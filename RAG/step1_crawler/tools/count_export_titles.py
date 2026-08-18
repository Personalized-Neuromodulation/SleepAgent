#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Count exported papers by journal family and subjournal using title as key."""

import argparse
import csv
import html
import json
import re
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = BASE_DIR / "exports" / "sleep"
DEFAULT_OUTPUT = DEFAULT_ROOT / "title_count_summary.csv"


def normalize_title(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def display_title(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_category(path):
    name = path.name.lower()
    if "_related_" in name:
        return "related"
    if "_review_failed_" in name:
        return "review_failed"
    return "other"


def read_csv_rows(path):
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error


def read_json_rows(path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def read_xlsx_rows(path):
    try:
        import pandas as pd
    except Exception as exc:
        raise RuntimeError("pandas is required to read xlsx exports") from exc
    return pd.read_excel(path).fillna("").to_dict("records")


def read_rows(path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv_rows(path)
    if suffix == ".json":
        return read_json_rows(path)
    if suffix in (".xlsx", ".xls"):
        return read_xlsx_rows(path)
    return []


def title_from_row(row):
    for key in ("title", "Title", "标题", "论文标题"):
        if key in row and str(row.get(key) or "").strip():
            return row.get(key)
    for key, value in row.items():
        if str(key or "").strip().lower() == "title" and str(value or "").strip():
            return value
    return ""


def new_bucket():
    return {
        "files": set(),
        "rows": 0,
        "missing_title_rows": 0,
        "titles": {},
    }


def add_row(bucket, file_path, row):
    bucket["files"].add(str(file_path))
    bucket["rows"] += 1
    title = title_from_row(row)
    key = normalize_title(title)
    if not key:
        bucket["missing_title_rows"] += 1
        return
    bucket["titles"].setdefault(key, display_title(title))


def scan_exports(root):
    root = Path(root)
    stats = defaultdict(lambda: defaultdict(lambda: defaultdict(new_bucket)))
    supported = {".csv", ".json", ".xlsx", ".xls"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in supported:
            continue
        relative = path.relative_to(root)
        if len(relative.parts) < 3:
            continue
        journal_type = relative.parts[0]
        subjournal = relative.parts[1]
        category = detect_category(path)
        rows = read_rows(path)
        bucket = stats[journal_type][subjournal][category]
        if not rows:
            bucket["files"].add(str(path))
        for row in rows:
            add_row(bucket, path, row)
    return stats


def bucket_count(bucket):
    return {
        "files": len(bucket["files"]),
        "rows": bucket["rows"],
        "unique_titles": len(bucket["titles"]),
        "missing_title_rows": bucket["missing_title_rows"],
    }


def build_summary_rows(stats):
    rows = []
    type_totals = defaultdict(lambda: defaultdict(new_bucket))
    for journal_type in sorted(stats):
        for subjournal in sorted(stats[journal_type]):
            categories = stats[journal_type][subjournal]
            related = bucket_count(categories.get("related", new_bucket()))
            review_failed = bucket_count(categories.get("review_failed", new_bucket()))
            other = bucket_count(categories.get("other", new_bucket()))

            total_titles = {}
            total_files = set()
            total_rows = 0
            total_missing = 0
            for category, bucket in categories.items():
                total_titles.update(bucket["titles"])
                total_files.update(bucket["files"])
                total_rows += bucket["rows"]
                total_missing += bucket["missing_title_rows"]
                type_bucket = type_totals[journal_type][category]
                type_bucket["files"].update(bucket["files"])
                type_bucket["rows"] += bucket["rows"]
                type_bucket["missing_title_rows"] += bucket["missing_title_rows"]
                type_bucket["titles"].update(bucket["titles"])

            rows.append({
                "journal_type": journal_type,
                "subjournal": subjournal,
                "related_files": related["files"],
                "related_rows": related["rows"],
                "related_unique_titles": related["unique_titles"],
                "review_failed_files": review_failed["files"],
                "review_failed_rows": review_failed["rows"],
                "review_failed_unique_titles": review_failed["unique_titles"],
                "other_files": other["files"],
                "other_rows": other["rows"],
                "other_unique_titles": other["unique_titles"],
                "total_files": len(total_files),
                "total_rows": total_rows,
                "total_unique_titles": len(total_titles),
                "duplicate_title_rows": max(0, total_rows - total_missing - len(total_titles)),
                "missing_title_rows": total_missing,
            })

    total_rows = []
    for journal_type in sorted(type_totals):
        categories = type_totals[journal_type]
        total_titles = {}
        total_files = set()
        total_count = 0
        missing_count = 0
        for bucket in categories.values():
            total_titles.update(bucket["titles"])
            total_files.update(bucket["files"])
            total_count += bucket["rows"]
            missing_count += bucket["missing_title_rows"]
        total_rows.append({
            "journal_type": journal_type,
            "subjournals": len(stats.get(journal_type, {})),
            "files": len(total_files),
            "rows": total_count,
            "unique_titles": len(total_titles),
            "duplicate_title_rows": max(0, total_count - missing_count - len(total_titles)),
            "missing_title_rows": missing_count,
        })
    return rows, total_rows


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "journal_type",
        "subjournal",
        "related_files",
        "related_rows",
        "related_unique_titles",
        "review_failed_files",
        "review_failed_rows",
        "review_failed_unique_titles",
        "other_files",
        "other_rows",
        "other_unique_titles",
        "total_files",
        "total_rows",
        "total_unique_titles",
        "duplicate_title_rows",
        "missing_title_rows",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_totals(total_rows):
    print("journal_type,subjournals,files,rows,unique_titles,duplicate_title_rows,missing_title_rows")
    for row in total_rows:
        print(
            "{journal_type},{subjournals},{files},{rows},{unique_titles},{duplicate_title_rows},{missing_title_rows}".format(
                **row
            )
        )


def main():
    parser = argparse.ArgumentParser(description="Count exported papers by title under exports/sleep.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Export topic directory, default: exports/sleep")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path")
    args = parser.parse_args()

    stats = scan_exports(args.root)
    detail_rows, total_rows = build_summary_rows(stats)
    write_csv(args.output, detail_rows)
    print_totals(total_rows)
    print("detail_csv={}".format(Path(args.output).resolve()))


if __name__ == "__main__":
    main()
