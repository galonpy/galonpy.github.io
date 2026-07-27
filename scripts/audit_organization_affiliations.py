#!/usr/bin/env python3

"""Verify that each displayed organization is printed in its linked publication."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_ROOT / "_data" / "research_use.yml"
PDF_DIR = REPO_ROOT / "tmp" / "pdfs" / "org-audit"
OUTPUT_PATH = REPO_ROOT / "_research" / "organization_affiliation_audit.csv"

ALIASES = {
    "UC Berkeley": ["University of California, Berkeley"],
    "UCLA": ["University of California, Los Angeles", "UCLA"],
    "University of Illinois, Urbana-Champaign": [
        "University of Illinois, Urbana-Champaign"
    ],
    "Hong Kong University of Science and Technology": [
        "Hong Kong University of Science and Technology"
    ],
    "The Ohio State University": ["The Ohio State University"],
    "The University of Melbourne": ["The University of Melbourne"],
    "International Digital Economy Academy (IDEA)": [
        "International Digital Economy Academy"
    ],
    "Allen Institute for AI": ["Allen Institute for AI"],
    "Samsung R&D": ["Samsung R&D", "Samsung Research"],
    "Google DeepMind": ["Google DeepMind"],
    "Carnegie Mellon": ["Carnegie Mellon University"],
    "MIT": ["Massachusetts Institute of Technology", "MIT"],
    "Harvard": ["Harvard University"],
    "Pennsylvania State University": ["Pennsylvania State University"],
    "Shanghai Artificial Intelligence Laboratory": [
        "Shanghai Artificial Intelligence Laboratory"
    ],
}


def normalized_url(url: str) -> str:
    return re.sub(r"#page=1$", "", url).replace("http://", "https://", 1)


def local_pdf(url: str) -> Path:
    digest = hashlib.sha256(normalized_url(url).encode()).hexdigest()[:16]
    return PDF_DIR / f"{digest}.pdf"


def first_page_text(path: Path) -> str:
    return re.sub(r"\s+", " ", PdfReader(str(path)).pages[0].extract_text() or "").strip()


def evidence_excerpt(text: str, match: re.Match[str]) -> str:
    left = max(0, match.start() - 140)
    right = min(len(text), match.end() + 180)
    return text[left:right].strip()


def main() -> int:
    yaml_json = subprocess.run(
        [
            "ruby",
            "-ryaml",
            "-rjson",
            "-e",
            "puts JSON.generate(YAML.load_file(ARGV.fetch(0)))",
            str(DATA_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    research_use = json.loads(yaml_json)["llmattacks"]
    output_rows = []
    failures = []

    for group in ("companies", "universities"):
        for organization in research_use[group]:
            name = organization["name"]
            path = local_pdf(organization["url"])
            basis = organization.get("evidence_basis", "author_affiliation")
            matched_name = ""
            excerpt = ""
            status = "failed"

            if path.exists():
                text = first_page_text(path)
                for alias in ALIASES.get(name, [name]):
                    match = re.search(re.escape(alias), text, re.IGNORECASE)
                    if match:
                        matched_name = match.group(0)
                        excerpt = evidence_excerpt(text, match)
                        status = "verified"
                        break

                if basis == "workshop_host":
                    match = re.search(r"workshop held at Google", text, re.IGNORECASE)
                    if match:
                        matched_name = match.group(0)
                        excerpt = evidence_excerpt(text, match)
                        status = "verified_exception"

            row = {
                "group": group,
                "organization": name,
                "paper": organization["paper"],
                "publication_url": organization["url"],
                "status": status,
                "evidence_basis": basis,
                "explicit_name_matched": matched_name,
                "publication_excerpt": excerpt,
                "checked_on": date.today().isoformat(),
            }
            output_rows.append(row)
            failures.append(row) if status == "failed" else None

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=output_rows[0].keys(),
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {len(output_rows)} audit records to {OUTPUT_PATH}")
    print(f"Verified: {len(output_rows) - len(failures)}; failed: {len(failures)}")
    for failure in failures:
        print(f"FAIL {failure['group']}: {failure['organization']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
