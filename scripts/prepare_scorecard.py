"""Build the two small, redistributable catalog CSVs from Department of Education ZIPs."""

import argparse
import csv
import gzip
import io
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

# 50 states, DC and US territories. Freely associated sovereign states are outside scope.
STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
             "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split())
SCHOOL_FIELDS = {
    "name": "INSTNM", "city": "CITY", "state": "STABBR", "region": "REGION", "ownership": "CONTROL",
    "predominant_degree": "PREDDEG", "enrollment_undergrad": "UGDS", "admission_rate": "ADM_RATE",
    "sat_average": "SAT_AVG", "tuition_in_state": "TUITIONFEE_IN", "tuition_out_of_state": "TUITIONFEE_OUT",
    "median_earnings_10yr": "MD_EARN_WNE_P10", "median_debt": "GRAD_DEBT_MDN",
}


def read_archive(path, filename):
    with ZipFile(path) as archive, archive.open(filename) as stream, io.TextIOWrapper(
        stream, encoding="utf-8-sig", newline=""
    ) as source:
        yield from csv.DictReader(source)


def nullable(value):
    return "" if value in {"NULL", "NA", "PS", "PrivacySuppressed", ""} else value


def school_record(row):
    record = {field: nullable(row[column]) for field, column in SCHOOL_FIELDS.items()}
    url = nullable(row["INSTURL"]).strip()
    if url and "://" not in url:
        url = "https://" + url
    record["school_url"] = url if urlsplit(url).scheme in {"http", "https"} else ""
    record["cost_attendance"] = nullable(row["COSTT4_A"]) or nullable(row["COSTT4_P"])
    # These two measures use different federal fields at four-year and shorter institutions.
    if row["ICLEVEL"] in {"1", "2", "3"}:
        four_year = row["ICLEVEL"] == "1"
        record["completion_rate_150"] = nullable(row["C150_4"] if four_year else row["C150_L4"])
        record["retention_rate"] = nullable(row["RET_FT4"] if four_year else row["RET_FTL4"])
    else:
        record.update(completion_rate_150="", retention_rate="")
    return {"unitid": row["UNITID"], **record}


def write_csv(path, rows):
    with path.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as dest:
            writer = csv.DictWriter(dest, fieldnames=rows[0], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def prepare(schools_zip, fields_zip, output):
    schools = {}
    bachelor = set()
    for row in read_archive(schools_zip, "Most-Recent-Cohorts-Institution.csv"):
        if row["CURROPER"] != "1" or row["STABBR"] not in STATES:
            continue
        unitid = row["UNITID"]
        schools[unitid] = school_record(row)
        if row["HIGHDEG"] == "3" or row["PREDDEG"] == "3" or any(
            col.endswith("BACHL") and col.startswith("CIP") and value in {"1", "2"} for col, value in row.items()
        ):
            bachelor.add(unitid)

    counts = Counter()
    programs = {}
    for row in read_archive(fields_zip, "Most-Recent-Cohorts-Field-of-Study.csv"):
        if row["CREDLEV"] != "3":
            continue
        counts["bachelor_source_rows"] += 1
        unitid = row["UNITID"]
        if not unitid.isdecimal():
            counts["missing_unitid"] += 1
            continue
        if unitid not in schools:
            counts["outside_current_school_scope"] += 1
            continue
        cip = row["CIPCODE"]
        if not re.fullmatch(r"[0-9]{4}", cip) or (unitid, cip) in programs:
            raise ValueError(f"Invalid or duplicate CIP for {unitid}: {cip}")
        bachelor.add(unitid)
        programs[unitid, cip] = {"unitid": unitid, "cip_code": cip, "name": row["CIPDESC"], "credential_level": 3}
    if not programs:
        raise ValueError("No matching bachelor's fields")
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "institutions.csv.gz", [schools[key] for key in sorted(bachelor)])
    write_csv(output / "programs.csv.gz", [programs[key] for key in sorted(programs)])
    print(json.dumps(dict(counts, institutions=len(bachelor), programs=len(programs)), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("institutions_zip", type=Path)
    parser.add_argument("field_of_study_zip", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.institutions_zip, args.field_of_study_zip, args.output)
