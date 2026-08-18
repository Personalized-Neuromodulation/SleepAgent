#!/usr/bin/env python3
"""Summarize sleep-related papers and downloaded full-text formats."""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Set, Tuple


DEFAULT_ROOT = Path(r"D:\crawler2025\crawler_light\exports_811\sleep")
TARGET_FORMATS = ("pdf", "xml", "md", "json", "txt")
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")


@dataclass(frozen=True)
class JournalStats:
    journal_type: str
    csv_files: int = 0
    paper_rows: int = 0
    unique_dois: int = 0
    pdf: int = 0
    xml: int = 0
    md: int = 0
    json: int = 0
    txt: int = 0
    html: int = 0
    other: int = 0

    @property
    def fulltext_total(self) -> int:
        return self.pdf + self.xml + self.md + self.json + self.txt


@dataclass(frozen=True)
class SummaryReport:
    root: Path
    rows: Sequence[JournalStats]
    total: JournalStats


def normalize_doi(value: str) -> str:
    doi = (value or "").strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi.strip()


def read_csv_rows(path: Path) -> Tuple[List[dict], List[str]]:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                return list(reader), list(reader.fieldnames or [])
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Cannot decode CSV file {path}: {last_error}")


def find_doi_column(fieldnames: Iterable[str]) -> str | None:
    return next((name for name in fieldnames if name.strip().casefold() == "doi"), None)


def summarize_journal_type(journal_dir: Path) -> Tuple[JournalStats, Set[str]]:
    subjournal_dirs = sorted(
        (path for path in journal_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )
    csv_paths = sorted(
        path
        for subjournal_dir in subjournal_dirs
        for path in subjournal_dir.glob("sleep_related*.csv")
        if path.is_file()
    )
    paper_rows = 0
    dois: Set[str] = set()

    for csv_path in csv_paths:
        rows, fieldnames = read_csv_rows(csv_path)
        paper_rows += len(rows)
        doi_column = find_doi_column(fieldnames)
        if not doi_column:
            continue
        for row in rows:
            doi = normalize_doi(row.get(doi_column, ""))
            if doi:
                dois.add(doi)

    counts = {fmt: 0 for fmt in TARGET_FORMATS}
    html = 0
    other = 0
    for subjournal_dir in subjournal_dirs:
        fulltext_dir = subjournal_dir / "full_text"
        if not fulltext_dir.is_dir():
            continue
        for path in fulltext_dir.rglob("*"):
            if not path.is_file():
                continue
            extension = path.suffix.lower().lstrip(".")
            if extension in counts:
                counts[extension] += 1
            elif extension == "html":
                html += 1
            else:
                other += 1

    stats = JournalStats(
        journal_type=journal_dir.name,
        csv_files=len(csv_paths),
        paper_rows=paper_rows,
        unique_dois=len(dois),
        pdf=counts["pdf"],
        xml=counts["xml"],
        md=counts["md"],
        json=counts["json"],
        txt=counts["txt"],
        html=html,
        other=other,
    )
    return stats, dois


def summarize_root(root: Path) -> SummaryReport:
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Root directory does not exist: {root}")

    rows: List[JournalStats] = []
    global_dois: Set[str] = set()
    for journal_dir in sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    ):
        stats, dois = summarize_journal_type(journal_dir)
        rows.append(stats)
        global_dois.update(dois)

    total = JournalStats(
        journal_type="ALL",
        csv_files=sum(row.csv_files for row in rows),
        paper_rows=sum(row.paper_rows for row in rows),
        unique_dois=len(global_dois),
        pdf=sum(row.pdf for row in rows),
        xml=sum(row.xml for row in rows),
        md=sum(row.md for row in rows),
        json=sum(row.json for row in rows),
        txt=sum(row.txt for row in rows),
        html=sum(row.html for row in rows),
        other=sum(row.other for row in rows),
    )
    return SummaryReport(root=root, rows=rows, total=total)


def table_rows(report: SummaryReport) -> List[List[str]]:
    items = [*report.rows, report.total]
    return [
        [
            item.journal_type,
            str(item.csv_files),
            str(item.paper_rows),
            str(item.unique_dois),
            str(item.pdf),
            str(item.xml),
            str(item.md),
            str(item.json),
            str(item.txt),
            str(item.fulltext_total),
            str(item.html),
            str(item.other),
        ]
        for item in items
    ]


def print_report(report: SummaryReport) -> None:
    headers = [
        "journal_type", "csv_files", "paper_rows", "unique_dois",
        "pdf", "xml", "md", "json", "txt", "fulltext_total", "html", "other",
    ]
    rows = table_rows(report)
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def render(row: Sequence[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    print(f"Root: {report.root}")
    print(render(headers))
    print(render(["-" * width for width in widths]))
    for row in rows:
        print(render(row))


def write_report_csv(report: SummaryReport, output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "journal_type", "csv_files", "paper_rows", "unique_dois",
        "pdf", "xml", "md", "json", "txt", "fulltext_total", "html", "other",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in [*report.rows, report.total]:
            row = asdict(item)
            row["fulltext_total"] = item.fulltext_total
            writer.writerow(row)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize sleep_related CSV rows and full_text file formats by journal type."
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Sleep export root directory (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional UTF-8 CSV output path.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = summarize_root(args.root)
    print_report(report)
    if args.output:
        write_report_csv(report, args.output)
        print(f"CSV written: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
