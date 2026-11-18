"""Collect verified federal field links from known, campus-specific official catalog indexes."""

import argparse
import csv
import gzip
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

DATA = Path(__file__).resolve().parents[1] / "core/data"
AGENT = "AdmitCompassCatalog/1.0"
DEGREE = (r"(?:bachelor of (?:arts|science|fine arts|music|engineering|business administration)"
          r"|b(?:a|s|fa|ba|mus|sc|eng|sm|slas|sba|sw)|sb)")
DEGREE_SUFFIX = re.compile(rf"\s*(?:,\s*|\s+-\s*|\s+|\s*\()({DEGREE})(?:\s+(?:or|and)\s+{DEGREE})?"
                           r"(?:, course [\w-]+)?\)?$", re.I)
DEGREE_PREFIX = re.compile(rf"^{DEGREE}\s+(?:with a major |major )?in\s+", re.I)
NON_MAJOR = re.compile(r"\b(minor|certificate|graduate minor|dual degree|combined degree)\b", re.I)


def tidy(text):
    return " ".join(text.replace("\u200b", "").replace("\xad", "").replace(".", "").split()).casefold()


def name_key(text):
    text = tidy(text)
    text = re.sub(r"\s*\(course [0-9a-z-]+\)$", "", text)
    text = re.sub(r"\s+-\s+(bachelor of [a-z ]+)\s+\([a-z]+\)$", r", \1", text)
    text = DEGREE_PREFIX.sub("", DEGREE_SUFFIX.sub("", text))
    text = re.sub(r"(?:, general| major)$", "", text)
    return " ".join(text.replace("&", " and ").split())


class SameHost(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).hostname != urlsplit(req.full_url).hostname or urlsplit(newurl).scheme != "https":
            raise ValueError("Off-site catalog redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Reader:
    def __init__(self, index):
        self.opener = build_opener(SameHost())
        self.last = 0
        self.rules = RobotFileParser()
        self.delay = 0.35
        robots = urljoin(index, "/robots.txt")
        try:
            _, body = self.read(robots)
        except HTTPError as error:
            if error.code not in (404, 410):
                raise
            body = b""
        self.rules.parse(body.decode("utf-8", "replace").splitlines())
        self.delay = max(self.delay, self.rules.crawl_delay(AGENT) or self.rules.crawl_delay("*") or 0)

    def read(self, url):
        time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        with self.opener.open(Request(url, headers={"User-Agent": AGENT}), timeout=12) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
            return response.url, response.read(5_000_000)

    def page(self, url):
        if not self.rules.can_fetch(AGENT, url):
            raise ValueError("robots.txt exclusion")
        final, body = self.read(url)
        if not body:
            raise ValueError("Empty response")
        return final, BeautifulSoup(body, "html.parser")


def catalog_candidates(source, page, names):
    found = defaultdict(set)
    index = source["index_url"]
    for anchor in page.select(source["selector"]):
        url = urldefrag(urljoin(index, anchor["href"])).url
        url = url.removesuffix("index.html") if url.endswith("/index.html") else url
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != urlsplit(index).netloc
                or not parsed.path.startswith(source["path_prefix"]) or parsed.query
                or parsed.path.rstrip("/") == urlsplit(index).path.rstrip("/")):
            continue
        if source["unitid"] == "150136" and (
            not re.search(r"/(?:academic-programs|undergraduate-majors|bachelors-degrees)/", parsed.path)
            or "concentration" in parsed.path
        ):
            continue
        label = (anchor.select_one(".title, .item-name") or anchor).get_text(" ", strip=True)
        if source["format"] == "degree_list" and re.fullmatch(DEGREE, tidy(label)):
            item = anchor.find_parent("li")
            if item:
                label = f"{item.find(string=True, recursive=False) or ''} {label}"
        text = tidy(label)
        if NON_MAJOR.search(text):
            continue
        has_degree = DEGREE_SUFFIX.search(text) or DEGREE_PREFIX.search(text)
        if source["format"] == "florida":
            has_degree = re.search(r"_(?:BA|BS|BFA|BMUS)(?:_(?:BA|BS))?/$", parsed.path)
        if source["format"] == "major":
            has_degree = text.endswith(" major")
        if not has_degree and source["format"] != "undergrad":
            continue
        key = name_key(text)
        if key in names:
            found[key].add(url)
    return found


def heading_confirms(page, key):
    labels = [h.get_text(" ", strip=True) for h in page.select("h1")]
    if page.title:
        title = page.title.get_text(" ", strip=True).removeprefix("General Catalog - ")
        labels.append(re.split(r" [|<] ", title, maxsplit=1)[0])
    return any(name_key(label) == key for label in labels)


def collect(source, fields):
    unitid = source["unitid"]
    rows = []
    names = defaultdict(list)
    for row in fields:
        names[name_key(row["name"])].append(row["cip_code"])
    reader = Reader(source["index_url"])
    _, page = reader.page(source["index_url"])
    candidates = catalog_candidates(source, page, names)
    errors = 0
    for key, urls in sorted(candidates.items()):
        if len(urls) != 1 or len(names[key]) != 1:
            continue
        try:
            final, detail = reader.page(next(iter(urls)))
            if (urlsplit(final).path.startswith(source["path_prefix"]) and heading_confirms(detail, key)):
                rows.append((unitid, names[key][0], "3", final))
        except (HTTPError, URLError, TimeoutError, ValueError):
            errors += 1
    print(f"{unitid} {urlsplit(source['index_url']).hostname}: {len(rows)} verified; "
          f"{errors} detail pages unavailable", flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with (DATA / "catalog_directories.csv").open() as stream:
        sources = list(csv.DictReader(stream))
    fields = defaultdict(list)
    with gzip.open(DATA / "scorecard_2026/programs.csv.gz", "rt") as stream:
        for row in csv.DictReader(stream):
            fields[row["unitid"]].append(row)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(collect, source, fields[source["unitid"]]) for source in sources]
        results = []
        for source, future in zip(sources, futures, strict=True):
            try:
                results.extend(future.result())
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                print(f"{source['unitid']} index unavailable: {error}", flush=True)
    if not results:
        raise SystemExit("No verified links; snapshot was not written")
    temporary = args.output.with_suffix(".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["unitid", "cip_code", "credential_level", "catalog_url"])
        writer.writerows(sorted(results))
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
