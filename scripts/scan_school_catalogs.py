"""Discover undergraduate catalog links by following public links from Scorecard school homepages."""

import argparse
import asyncio
import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import aiohttp
from lxml import etree, html

from scripts.collect_program_links import AGENT, DATA, DEGREE_PREFIX, DEGREE_SUFFIX, NON_MAJOR, name_key, tidy

INDEX = re.compile(r"majors?|programs?|fields of study|degrees?|academics?|course catalog|undergraduate", re.I)
EXCLUDED = re.compile(r"\b(graduate|masters?|doctoral|minor|certificate|admissions?|apply|financial aid|online only|"
                      r"news|events|athletics|faculty|staff|research|alumni|course descriptions)\b", re.I)
DEGREE_PATH = re.compile(r"(?:[-/_])(?:ba|bs|bfa|bba|bsw|bsc|bmus)(?:[-/]|$)", re.I)


def host(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def site(url):
    # Subdomains of US .edu registrations can host the university's catalog.
    domain = host(url)
    return ".".join(domain.split(".")[-2:]) if domain.endswith(".edu") else domain


def official(url, home):
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.username is None and parts.password is None
            and parts.port in (None, 443) and site(url) == site(home) and not parts.fragment)


def eligible_url(base, href, home):
    try:
        url = urldefrag(urljoin(base, href.strip()))[0]
        parsed = urlsplit(url)
        if parsed.scheme == "http":
            url = "https://" + url.split("://", 1)[1]
        if (not official(url, home) or len(url) > 600 or parsed.query
                or re.search(r"\.(?:pdf|docx?|xlsx?|png|jpg|gif|zip)$", parsed.path, re.I)):
            return None
        return url
    except ValueError:
        return None


class Web:
    def __init__(self, session):
        self.session = session
        self.rules = {}
        self.locks = defaultdict(asyncio.Lock)
        self.last = defaultdict(float)

    async def get(self, url):
        async with self.session.get(url, allow_redirects=False) as response:
            if 300 <= response.status < 400:
                return response.status, response.headers.get("Location", ""), b""
            if response.status != 200:
                return response.status, "", b""
            body = await response.content.read(1)  # also handles empty 200 responses
            if body:
                data = bytearray(body)
                async for chunk in response.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data) > 4_000_000:
                        raise ValueError("oversized_page")
                body = bytes(data)
            return response.status, "", body

    async def page(self, url, home):
        for _ in range(4):
            domain = urlsplit(url).netloc
            async with self.locks[domain]:
                if domain not in self.rules:
                    robots = RobotFileParser()
                    origin = urljoin(url, "/robots.txt")
                    for _hop in range(4):
                        status, dest, body = await self.get(origin)
                        if status in (301, 302, 303, 307, 308):
                            origin = eligible_url(origin, dest, home)
                            if not origin:
                                raise ValueError("robots_redirect")
                            continue
                        break
                    if status in (404, 410):
                        body = b""
                    elif status != 200:
                        raise ValueError("robots_http_" + str(status))
                    robots.parse(body.decode("utf-8", "replace").splitlines())
                    self.rules[domain] = robots
                robots = self.rules[domain]
                if not robots.can_fetch(AGENT, url):
                    raise ValueError("robots_excluded")
                delay = max(0.4, robots.crawl_delay(AGENT) or robots.crawl_delay("*") or 0)
                if delay > 60:
                    raise ValueError("deferred_site_interval")
                now = asyncio.get_running_loop().time
                await asyncio.sleep(max(0, self.last[domain] + delay - now()))
                self.last[domain] = now()
                status, dest, body = await self.get(url)
            if status in (301, 302, 303, 307, 308):
                url = eligible_url(url, dest, home)
                if not url:
                    raise ValueError("outside_official_site")
                continue
            if status != 200 or not body:
                raise ValueError("page_http_" + str(status))
            try:
                page = html.fromstring(body)
            except etree.ParserError as error:
                raise ValueError("unreadable_html") from error
            return url, page
        raise ValueError("redirect_limit")


def text(node):
    return " ".join(node.text_content().split())


def heading_evidence(page, key):
    headings = [text(h) for h in page.xpath("//h1")]
    for t in page.xpath("//title"):
        headings.append(re.split(r" [|<–—] ", text(t), maxsplit=1)[0])
    exact = [h for h in headings if name_key(h) == key]
    degree = any(DEGREE_PREFIX.search(tidy(h)) or DEGREE_SUFFIX.search(tidy(h)) for h in exact)
    return bool(exact), degree


def index_rank(label, url):
    path = urlsplit(url).path.lower().replace("-", " ").replace("_", " ")
    label = label.strip()
    if not label or len(label) > 90 or EXCLUDED.search(label) or EXCLUDED.search(path):
        return 0
    if not INDEX.search(label):
        return 0
    if re.search(r"majors|undergraduate (?:programs|degrees)|areas of study|program finder", label, re.I):
        return 5
    if re.fullmatch(r"(?:all |academic |degree |explore )?(?:programs|degrees)(?: of study)?", label, re.I):
        return 4
    if re.search(r"catalog|academics|undergraduate", label, re.I):
        return 3
    return 0


def campus_specific(url, home, peers):
    """Shared school systems must have a campus-specific host or non-overlapping URL path."""
    if host(url) != host(home):
        return False
    same_host = [peer for peer in peers if host(peer) == host(home)]
    if len(same_host) == 1 and host(home) != site(home):
        return True
    prefix = urlsplit(home).path.rstrip("/")
    if not prefix or sum(urlsplit(p).path.rstrip("/") == prefix for p in same_host) != 1:
        return False
    path = urlsplit(url).path.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def bachelor_evidence(page):
    # Degree evidence in page headings or structured award labels, never in menus or site footers.
    for node in page.xpath("//main//*[self::h2 or self::h3 or self::dd or self::dt]"):
        if node.xpath("ancestor::nav|ancestor::footer"):
            continue
        label = tidy(text(node))
        if len(label) < 150 and re.search(r"\bbachelor(?:'s)? (?:of|degree)\b", label):
            return True
    return False


async def scan(school, fields, web, shared, extended=False):
    home = school["school_url"]
    result = {"unitid": school["unitid"], "status": "", "pages": 0, "details": 0, "matches": []}
    if not home or not fields:
        result["status"] = "missing_homepage" if not home else "no_federal_fields"
        return result
    peers = shared.get(site(home), [])
    ambiguous_site = len(peers) > 1
    names = defaultdict(list)
    for r in fields:
        names[name_key(r["name"])].append(r["cip_code"])
    queue = {home: 99}
    seen = set()
    candidates = defaultdict(dict)
    errors = []
    budget = 10 if extended else 5
    while queue and len(seen) < budget:
        url = max(queue, key=queue.get)
        queue.pop(url)
        if url in seen:
            continue
        seen.add(url)
        try:
            final, page = await web.page(url, home)
        except (OSError, aiohttp.ClientError, ValueError, TimeoutError) as error:
            errors.append(str(error)[:60] or type(error).__name__)
            continue
        result["pages"] += 1
        seen.add(final)
        if ambiguous_site and (not extended or not campus_specific(home, home, peers)):
            result["status"] = "shared_campus_domain"
            return result
        directory_title = " ".join(text(t) for t in page.xpath("//title|//h1"))
        undergraduate = bool(re.search(r"undergraduate (?:majors|programs|degrees)|bachelor.s (?:degrees|programs)",
                                       directory_title, re.I))
        for anchor in page.xpath("//a[@href]"):
            label = text(anchor)
            if not label or len(label) > 120:
                continue
            target = eligible_url(final, anchor.get("href"), home)
            if not target or target == final:
                continue
            if ambiguous_site and not campus_specific(target, home, peers):
                continue
            key = name_key(label)
            if key in names and len(names[key]) == 1 and not NON_MAJOR.search(label):
                evidence = bool(DEGREE_PREFIX.search(tidy(label)) or DEGREE_SUFFIX.search(tidy(label)))
                # Skip department homepages and links from unrelated navigation blocks.
                path = urlsplit(target).path.lower()
                specific = bool(re.search(r"major|degrees?|program|undergrad|/catalog/", path) or DEGREE_PATH.search(path))
                if extended and re.search(r"/(?:academics|study|fields-of-study)/[^/]+", path):
                    specific = True
                if (evidence or specific or undergraduate) and not EXCLUDED.search(path.replace("-", " ")):
                    previous = candidates[key].get(target)
                    if not previous or (evidence, undergraduate) > previous[1:]:
                        candidates[key][target] = (final, evidence, undergraduate)
            rank = index_rank(label, target)
            if extended and not rank and re.fullmatch(
                r"areas of study|explore (?:our )?(?:majors|programs)|fields of study|what to study", label, re.I
            ):
                rank = 5
            if target not in seen and rank:
                queue[target] = max(rank, queue.get(target, 0))
    for key, urls in candidates.items():
        if len(urls) != 1:
            continue
        url, (index, degree_in_label, undergraduate) = next(iter(urls.items()))
        try:
            final, page = await web.page(url, home)
        except (OSError, aiohttp.ClientError, ValueError, TimeoutError):
            continue
        result["details"] += 1
        exact, degree_in_title = heading_evidence(page, key)
        path = urlsplit(final).path.casefold()
        if EXCLUDED.search(path.replace("-", " ")):
            continue
        major_page = bool(re.search(r"/(?:majors?|degrees?|programs?)/[^/]+|(?:-major|-degree|/bachelors?)/?$", path)
                          or DEGREE_PATH.search(path))
        degree_on_page = extended and major_page and bachelor_evidence(page)
        if ambiguous_site and not campus_specific(final, home, peers):
            continue
        if exact and (degree_in_title or (degree_in_label and major_page) or (undergraduate and major_page)
                      or degree_on_page):
            result["matches"].append([names[key][0], final, index])
    if result["matches"]:
        result["status"] = "matched"
    elif result["pages"]:
        result["status"] = "no_verified_match"
    else:
        result["status"] = "deferred_site_interval" if "deferred_site_interval" in errors else "homepage_unavailable"
    if errors:
        result["error"] = errors[0]
    return result


async def run(cache, retry_from=None, offset=0, limit=None):
    cache.mkdir(parents=True, exist_ok=True)
    snapshot = DATA / "scorecard_2026"
    with gzip.open(snapshot / "institutions.csv.gz", "rt") as stream:
        schools = list(csv.DictReader(stream))
    with (DATA / "catalog_directories.csv").open() as stream:
        prior = {r["unitid"] for r in csv.DictReader(stream)}
    fields = defaultdict(list)
    with gzip.open(snapshot / "programs.csv.gz", "rt") as stream:
        for field in csv.DictReader(stream):
            fields[field["unitid"]].append(field)
    shared = defaultdict(list)
    for s in schools:
        shared[site(s["school_url"])].append(s["school_url"])
    timeout = aiohttp.ClientTimeout(total=10, connect=5)
    async with aiohttp.ClientSession(headers={"User-Agent": AGENT}, timeout=timeout,
                                    connector=aiohttp.TCPConnector(limit=64), trust_env=True) as session:
        web = Web(session)
        queue = asyncio.Queue()
        remaining = [s for s in schools if s["unitid"] not in prior]
        for school in remaining[offset:offset + limit if limit is not None else None]:
            path = cache / (school["unitid"] + ".json")
            if path.exists():
                continue
            if retry_from:
                if not (retry_from / path.name).exists():
                    raise ValueError(f"Complete the first-pass batch before retrying UNITID {school['unitid']}")
                old = json.loads((retry_from / path.name).read_text())
                if old["status"] in {"matched", "no_federal_fields", "missing_homepage", "deferred_site_interval"}:
                    path.write_text(json.dumps(old))
                    continue
            queue.put_nowait(school)

        async def worker():
            while not queue.empty():
                school = queue.get_nowait()
                result = await scan(school, fields[school["unitid"]], web, shared, extended=bool(retry_from))
                if retry_from:
                    old = json.loads((retry_from / (school["unitid"] + ".json")).read_text())
                    result["pages"] += old["pages"]
                    result["details"] += old["details"]
                    if result["status"] == "homepage_unavailable" and old["pages"]:
                        result["status"] = old["status"]
                path = cache / (school["unitid"] + ".json")
                temp = path.with_suffix(".tmp")
                temp.write_text(json.dumps(result))
                temp.replace(path)
        await asyncio.gather(*(worker() for _ in range(48)))


def export(cache, directory):
    with (DATA / "catalog_directories.csv").open() as stream:
        prior = {r["unitid"] for r in csv.DictReader(stream)}
    with gzip.open(DATA / "scorecard_2026/institutions.csv.gz", "rt") as stream:
        remaining = {r["unitid"]: r["name"] for r in csv.DictReader(stream) if r["unitid"] not in prior}
    reports, links = [], []
    for unit, school_name in sorted(remaining.items()):
        item = json.loads((cache / (unit + ".json")).read_text())
        if item["unitid"] != unit:
            raise ValueError(f"Checkpoint UNITID mismatch: {unit}")
        reports.append([unit, school_name, item["status"], item["pages"], item["details"], len(item["matches"])])
        for cip, url, source in sorted(item["matches"]):
            links.append([unit, cip, "3", url, source])
    for filename, columns, rows in [
        ("discovered_catalog_links.csv", ["unitid", "cip_code", "credential_level", "catalog_url", "index_url"], links),
        ("catalog_scan_coverage.csv", ["unitid", "school", "status", "pages", "details", "matches"], reports),
    ]:
        path = directory / filename
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", newline="") as outfile:
            writer = csv.writer(outfile, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows(rows)
        tmp.replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint_directory", type=Path)
    parser.add_argument("--retry-from", type=Path, help="Revisit first-pass nonmatches with a deeper catalog search.")
    parser.add_argument("--export", type=Path, help="Write snapshots from a completed scan without network access.")
    parser.add_argument("--offset", type=int, default=0, help="Start position within the remaining schools.")
    parser.add_argument("--limit", type=int, help="Maximum number of schools in this batch.")
    args = parser.parse_args()
    if args.offset < 0 or (args.limit is not None and args.limit < 1):
        parser.error("offset must be nonnegative and limit positive")
    if args.export:
        export(args.checkpoint_directory, args.export)
    else:
        asyncio.run(run(args.checkpoint_directory, args.retry_from, args.offset, args.limit))
