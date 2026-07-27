#!/usr/bin/env python3

"""Recover missing citation excerpts from locally downloaded citing-paper PDFs."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = REPO_ROOT / "tmp" / "pdfs" / "citation-recovery"
MISSING_TSV = Path("/tmp/missing_citations.tsv")
OUTPUT_PATH = REPO_ROOT / "_research" / "recovered_excerpts.json"

AUTHOR_PATTERN = re.compile(
    r"\bAlon\s*(?:,?\s+(?:and|&)\s+|,\s*)Kamfonas\b", re.IGNORECASE
)
TITLE_PATTERN = re.compile(
    r"Detecting\s+Language\s+Model\s+Attacks\s+with\s+Perplexity", re.IGNORECASE
)
REFERENCES_PATTERN = re.compile(r"(?:^|\n)\s*(?:references|bibliography)\s*(?:\n|$)", re.IGNORECASE)


def normalize(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\s*\n\s*(?=[a-z])", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def excerpt_around(text: str, start: int, end: int, radius: int = 360) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    window = normalize(text[left:right])
    local_start = max(0, start - left)
    local_end = min(len(window), end - left)

    before = window[:local_start]
    after = window[local_end:]
    sentence_left = max(
        before.rfind(". "),
        before.rfind("? "),
        before.rfind("! "),
        before.rfind("; "),
    )
    sentence_right_candidates = [
        index
        for marker in (". ", "? ", "! ", "; ")
        if (index := after.find(marker)) >= 0
    ]
    sentence_right = min(sentence_right_candidates) + 1 if sentence_right_candidates else len(after)
    result = window[sentence_left + 2 : local_end + sentence_right].strip()
    return result if len(result) >= 35 else window


def reference_start_page(page_texts: list[str]) -> int:
    for index, text in enumerate(page_texts):
        if REFERENCES_PATTERN.search(text):
            return index
    return max(0, int(len(page_texts) * 0.72))


def numeric_marker(reference_text: str, match_start: int) -> str | None:
    prefix = reference_text[max(0, match_start - 700) : match_start]
    candidates = list(
        re.finditer(r"(?:^|\n)\s*(?:\[(\d{1,3})\]|(\d{1,3})[.)])\s+", prefix)
    )
    if not candidates:
        return None
    match = candidates[-1]
    return match.group(1) or match.group(2)


def recover_from_pdf(pdf_path: Path) -> dict[str, object] | None:
    try:
        reader = PdfReader(str(pdf_path))
        raw_pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as error:  # malformed or unsupported PDFs remain explicitly missing
        return {"error": f"{type(error).__name__}: {error}"}

    pages = [normalize(text) for text in raw_pages]
    refs_at = reference_start_page(raw_pages)

    # Prefer an author-year citation in the body.
    for page_index, text in enumerate(pages[: max(refs_at + 1, 1)]):
        for match in AUTHOR_PATTERN.finditer(text):
            nearby = text[max(0, match.start() - 180) : match.end() + 260]
            if TITLE_PATTERN.search(nearby):
                continue
            return {
                "excerpt": excerpt_around(text, match.start(), match.end()),
                "page": page_index + 1,
                "method": "pdf_in_text_author_citation",
            }

    # Locate the bibliography entry, infer its numeric marker, then find that
    # marker in the body. This recovers papers that use numeric citation styles.
    reference_match: tuple[int, re.Match[str]] | None = None
    for page_index in range(refs_at, len(pages)):
        match = TITLE_PATTERN.search(raw_pages[page_index]) or AUTHOR_PATTERN.search(
            raw_pages[page_index]
        )
        if match:
            reference_match = (page_index, match)
            break

    if reference_match:
        reference_page, match = reference_match
        reference_text = raw_pages[reference_page]
        marker = numeric_marker(reference_text, match.start())
        if marker:
            marker_pattern = re.compile(rf"\[\s*{re.escape(marker)}\s*\]")
            for page_index, text in enumerate(pages[: max(refs_at, 1)]):
                body_match = marker_pattern.search(text)
                if body_match:
                    return {
                        "excerpt": excerpt_around(text, body_match.start(), body_match.end()),
                        "page": page_index + 1,
                        "method": "pdf_in_text_numeric_citation",
                        "reference_marker": marker,
                    }

        return {
            "excerpt": excerpt_around(
                reference_text, match.start(), match.end(), radius=240
            ),
            "page": reference_page + 1,
            "method": "pdf_bibliography_entry_only",
        }

    return None


def load_missing() -> list[dict[str, str]]:
    records = []
    with MISSING_TSV.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            paper_id, arxiv_id, acl_id, doi, title = (row + [""] * 5)[:5]
            records.append(
                {
                    "paper_id": paper_id,
                    "arxiv_id": arxiv_id,
                    "acl_id": acl_id,
                    "doi": doi,
                    "title": title,
                }
            )
    return records


def source_url(record: dict[str, str]) -> str:
    if record["arxiv_id"]:
        return f"https://arxiv.org/pdf/{record['arxiv_id']}#page=1"
    if record["acl_id"]:
        return f"https://aclanthology.org/{record['acl_id']}.pdf"
    if record["doi"]:
        return f"https://doi.org/{record['doi']}"
    return ""


def main() -> int:
    recovered: dict[str, dict[str, object]] = {}
    attempted = 0
    for record in load_missing():
        pdf_path = PDF_DIR / f"{record['paper_id']}.pdf"
        if not pdf_path.exists() or pdf_path.stat().st_size < 10_000:
            continue
        attempted += 1
        result = recover_from_pdf(pdf_path)
        if not result or "error" in result:
            continue
        result.update(
            {
                "title": record["title"],
                "source_url": source_url(record),
            }
        )
        recovered[record["paper_id"]] = result

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(recovered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Attempted {attempted} PDFs; recovered {len(recovered)} excerpts")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
