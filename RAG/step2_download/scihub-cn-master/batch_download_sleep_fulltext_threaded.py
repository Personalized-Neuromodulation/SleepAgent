#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import urllib3

from download import DEFAULT_EMAIL, DEFAULT_SOURCES, Downloader, Result, detect_encoding, normalize_doi, normalize_proxy, safe_name
from download_dois_from_csv import DEFAULT_COOKIE_FILE, load_mirror_cookies
from scihub_cn.scihub import SciHub


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
LOG = logging.getLogger("batch-fulltext")


DEFAULT_ROOT = Path(r"/data/RAG/step1_crawler/exports/sleep")
FAILURE_REPORT = "download_failures.csv"
SUMMARY_REPORT = "download_summary.csv"
RESULT_REPORT = "download_results.csv"
FULLTEXT_EXTENSIONS = {".pdf", ".html", ".xml", ".json", ".txt", ".md"}
FINAL_FORMAT_PRIORITY = {".pdf": 0, ".xml": 1, ".json": 2, ".md": 3}
JOURNAL_TYPE_PRIORITY = {
    "nature": 0,
    "cell": 1,
    "science": 2,
    "plos": 3,
    "other": 4,
}


class RateLimiter:
    def __init__(self, max_concurrent: int = 1, min_interval: float = 0.0) -> None:
        self.semaphore = threading.BoundedSemaphore(max(1, int(max_concurrent)))
        self.min_interval = max(0.0, float(min_interval))
        self.lock = threading.Lock()
        self.last_started = 0.0

    def __enter__(self):
        self.semaphore.acquire()
        if self.min_interval > 0:
            with self.lock:
                now = time.monotonic()
                wait = self.min_interval - (now - self.last_started)
                if wait > 0:
                    time.sleep(wait)
                self.last_started = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.semaphore.release()
        return False


class DownloadLimiters:
    def __init__(
        self,
        scihub_workers: int,
        semantic_interval: float,
        crossref_interval: float,
        unpaywall_interval: float,
        openalex_interval: float,
        pubmed_interval: float,
        europe_pmc_interval: float,
        pmc_interval: float,
        publisher_host_workers: int,
    ) -> None:
        self.scihub = RateLimiter(scihub_workers, 0.0)
        self.semantic_scholar = RateLimiter(1, semantic_interval)
        self.crossref = RateLimiter(1, crossref_interval)
        self.unpaywall = RateLimiter(1, unpaywall_interval)
        self.openalex = RateLimiter(1, openalex_interval)
        self.pubmed = RateLimiter(1, pubmed_interval)
        self.europe_pmc = RateLimiter(1, europe_pmc_interval)
        self.pmc = RateLimiter(1, pmc_interval)
        self.publisher_hosts: Dict[str, RateLimiter] = {}
        self.publisher_lock = threading.Lock()
        self.publisher_host_workers = max(1, int(publisher_host_workers))

    def publisher_for_doi(self, doi: str) -> RateLimiter:
        if doi.startswith("10.1038/"):
            host = "www.nature.com"
        elif doi.startswith("10.1126/"):
            host = "www.science.org"
        elif doi.startswith("10.1371/"):
            host = "journals.plos.org"
        elif doi.startswith("10.1016/"):
            host = "linkinghub.elsevier.com"
        else:
            host = "publisher:other"
        with self.publisher_lock:
            limiter = self.publisher_hosts.get(host)
            if limiter is None:
                limiter = RateLimiter(self.publisher_host_workers, 0.0)
                self.publisher_hosts[host] = limiter
            return limiter


class RateLimitedDownloader(Downloader):
    def __init__(self, *args, limiters: DownloadLimiters, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.limiters = limiters

    def publisher_pdf(self, doi: str, stem: str) -> Optional[Result]:
        with self.limiters.publisher_for_doi(doi):
            return super().publisher_pdf(doi, stem)

    def unpaywall(self, doi: str, stem: str) -> Optional[Result]:
        with self.limiters.unpaywall:
            return super().unpaywall(doi, stem)

    def openalex(self, doi: str, stem: str) -> Optional[Result]:
        with self.limiters.openalex:
            return super().openalex(doi, stem)

    def semantic_scholar(self, doi: str, stem: str) -> Optional[Result]:
        with self.limiters.semantic_scholar:
            return super().semantic_scholar(doi, stem)

    def crossref(self, doi: str, stem: str) -> Optional[Result]:
        with self.limiters.crossref:
            return super().crossref(doi, stem)

    def pubmed(self, doi: str, stem: str) -> Optional[Result]:
        with self.limiters.pubmed:
            return super().pubmed(doi, stem)

    def europe_pmc(self, doi: str, stem: str) -> Optional[Result]:
        with self.limiters.europe_pmc:
            return super().europe_pmc(doi, stem)

    def pmc(self, doi: str, stem: str) -> Optional[Result]:
        with self.limiters.pmc:
            return super().pmc(doi, stem)


@dataclass
class CsvJob:
    csv_path: Path
    journal_type: str
    sub_journal: str
    full_text_dir: Path
    all_info_path: Path


@dataclass
class PaperTask:
    job: CsvJob
    row: Dict[str, str]
    doi: str
    title: str


@dataclass
class DownloadOutcome:
    status: str
    source: str = ""
    fmt: str = ""
    file: str = ""
    error: str = ""



CSV_ENCODING = "utf-8-sig"


def _decode_mixed_csv_bytes(raw: bytes) -> str:
    """Decode a CSV that may contain UTF-8 and GB18030/GBK lines.

    Prefer UTF-8 per line. Only lines that are not valid UTF-8 fall back to
    GB18030, which also covers normal GBK text. This avoids converting valid
    UTF-8 punctuation/Chinese into mojibake while still recovering legacy rows.
    """
    if not raw:
        return ""

    decoded = []
    for index, bline in enumerate(raw.splitlines(keepends=True)):
        if index == 0 and bline.startswith(b"\xef\xbb\xbf"):
            bline = bline[3:]

        try:
            line = bline.decode("utf-8")
        except UnicodeDecodeError:
            try:
                line = bline.decode("gb18030")
            except UnicodeDecodeError:
                # Last-resort safety: never crash the whole batch because of
                # one damaged byte. The replacement is explicit and localized.
                line = bline.decode("utf-8", errors="replace")

        decoded.append(line)

    return "".join(decoded)


def ensure_csv_utf8_sig(path: Path) -> None:
    """Normalize an existing CSV to one encoding: UTF-8 with BOM.

    This is important before append mode. Appending UTF-8 rows to a legacy
    GBK/GB18030 CSV would otherwise create a mixed-encoding file.
    """
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return

    raw = path.read_bytes()

    # Fast path: a valid UTF-8/UTF-8-SIG file already needs no content repair.
    try:
        raw.decode("utf-8-sig")
        return
    except UnicodeDecodeError:
        pass

    normalized = _decode_mixed_csv_bytes(raw)

    # Rewrite atomically in the same directory.
    tmp = path.with_name(path.name + ".utf8fix.tmp")
    tmp.write_text(
        normalized,
        encoding=CSV_ENCODING,
        errors="strict",
        newline="",
    )
    tmp.replace(path)
    LOG.warning("Normalized mixed/legacy CSV to UTF-8-SIG: %s", path)


def safe_csv_text(value) -> str:
    """Return valid Unicode text for CSV output without byte-encoding ambiguity."""
    if value is None:
        return ""
    value = str(value)

    # Remove illegal lone surrogate code points if an upstream parser produced
    # them. Normal Unicode (Chinese, Greek letters, typographic punctuation,
    # etc.) remains unchanged.
    return value.encode("utf-8", errors="replace").decode("utf-8")


def safe_csv_row(row: Dict[str, object]) -> Dict[str, str]:
    return {
        str(key): safe_csv_text(value)
        for key, value in row.items()
    }


def safe_field(row: Dict[str, str], names: Sequence[str]) -> str:
    lower = {key.lower(): key for key in row}
    for name in names:
        key = lower.get(name.lower())
        if key:
            return (row.get(key) or "").strip()
    return ""


def read_rows(path: Path) -> List[Dict[str, str]]:
    raw = Path(path).read_bytes()
    text = _decode_mixed_csv_bytes(raw)
    return list(csv.DictReader(text.splitlines()))


def discover_jobs(root: Path) -> List[CsvJob]:
    jobs: List[CsvJob] = []
    for csv_path in sorted(root.rglob("sleep_related_*.csv")):
        rel = csv_path.relative_to(root)
        if len(rel.parts) < 3:
            continue
        journal_type, sub_journal = rel.parts[0], rel.parts[1]
        jobs.append(CsvJob(
            csv_path=csv_path,
            journal_type=journal_type,
            sub_journal=sub_journal,
            full_text_dir=csv_path.parent / "full_text",
            all_info_path=csv_path.parent / "all_info.csv",
        ))
    return sorted(
        jobs,
        key=lambda job: (
            JOURNAL_TYPE_PRIORITY.get(job.journal_type.lower(), 99),
            job.journal_type.lower(),
            job.sub_journal.lower(),
            str(job.csv_path).lower(),
        ),
    )


def iter_tasks(jobs: Iterable[CsvJob]) -> Iterable[PaperTask]:
    for job in jobs:
        for row in read_rows(job.csv_path):
            doi = normalize_doi(safe_field(row, ("doi", "DOI")))
            title = safe_field(row, ("title", "Title", "paper_title", "article_title"))
            if not doi:
                continue
            yield PaperTask(job=job, row=row, doi=doi, title=title)


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return len(read_rows(path))


def title_key(value: str) -> str:
    """
    Normalize an article title or a full-text filename to a stable comparison key.

    IMPORTANT:
    Do NOT use Path(value).stem here.

    Article titles may legally contain "/" or "\\", for example:
        The CHD8/CHD7/Kismet family ...

    Path(title).stem would interpret those characters as directory separators
    and truncate the logical title, causing duplicate cleanup to fail.

    Rules:
    1. Treat input as plain text.
    2. Remove only a known trailing full-text extension.
    3. Normalize all punctuation/separators to spaces.
    4. Collapse whitespace and lowercase.
    """
    value = str(value or "").strip()

    # Remove only a real final/transient full-text extension.
    # This works for both:
    #   task.title
    #   "Some title.pdf"
    # without interpreting "/" in a title as a path separator.
    value = re.sub(
        r"\.(pdf|xml|json|txt|html|md)$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(r"[^0-9a-z]+", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def matching_fulltext_files(full_text_dir: Path, title: str) -> List[Path]:
    """
    Return all full-text files belonging to the same logical article title.

    Matching is based on title_key(), which deliberately treats article titles
    as text rather than filesystem paths. This is essential for titles
    containing "/" or "\\".
    """
    key = title_key(title)
    if not key or not full_text_dir.exists():
        return []

    matches: List[Path] = []
    for path in full_text_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in FULLTEXT_EXTENSIONS:
            continue
        if title_key(path.name) == key:
            matches.append(path)

    return matches


def preferred_existing_file(full_text_dir: Path, title: str) -> Optional[Path]:
    """
    Return the best already-existing final-format file for this title.

    Priority:
        PDF > XML > JSON > MD

    HTML/TXT are transient/legacy formats and are not considered final.
    """
    candidates = [
        path for path in matching_fulltext_files(full_text_dir, title)
        if path.suffix.lower() in FINAL_FORMAT_PRIORITY
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda p: FINAL_FORMAT_PRIORITY[p.suffix.lower()])


def existing_pdf_for_title(full_text_dir: Path, title: str) -> Optional[Path]:
    for path in matching_fulltext_files(full_text_dir, title):
        if path.suffix.lower() == ".pdf":
            return path
    return None


def enforce_single_preferred_file(
    full_text_dir: Path,
    title: str,
    dry_run: bool = False,
) -> Tuple[Optional[Path], int]:
    """
    Keep exactly one same-title full-text file.

    Final priority:
        PDF > XML > JSON > MD

    Rules:
    - PDF wins over everything.
    - Without PDF, XML wins over JSON/MD.
    - Without XML, JSON wins over MD.
    - MD is the final fallback.
    - HTML/TXT are always removed once a final-format file exists.
    """
    files = matching_fulltext_files(full_text_dir, title)
    if not files:
        return None, 0

    final_candidates = [
        path for path in files
        if path.suffix.lower() in FINAL_FORMAT_PRIORITY
    ]
    if not final_candidates:
        return None, 0

    keep = min(
        final_candidates,
        key=lambda p: FINAL_FORMAT_PRIORITY[p.suffix.lower()],
    )

    removed = 0
    for path in files:
        if path == keep:
            continue
        if dry_run:
            LOG.info(
                "Would remove lower-priority duplicate: %s (keep %s)",
                path,
                keep,
            )
            removed += 1
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
            LOG.info(
                "Removed lower-priority duplicate: %s (keep %s)",
                path,
                keep,
            )
        except OSError as exc:
            LOG.warning("Could not remove duplicate %s: %s", path, exc)

    return keep, removed


def cleanup_preferred_files(full_text_dir: Path, dry_run: bool = False) -> int:
    """Clean an existing full_text directory to one preferred file per title."""
    if not full_text_dir.exists():
        return 0

    groups: Dict[str, List[Path]] = {}
    for path in full_text_dir.iterdir():
        if path.is_file() and path.suffix.lower() in FULLTEXT_EXTENSIONS:
            groups.setdefault(title_key(path.stem), []).append(path)

    removed = 0
    for files in groups.values():
        if not files:
            continue

        # We need at least one final-format file to safely collapse the group.
        final_candidates = [
            path for path in files
            if path.suffix.lower() in FINAL_FORMAT_PRIORITY
        ]
        if not final_candidates:
            continue

        keep = min(
            final_candidates,
            key=lambda p: FINAL_FORMAT_PRIORITY[p.suffix.lower()],
        )

        for path in files:
            if path == keep:
                continue
            if dry_run:
                LOG.info(
                    "Would remove lower-priority duplicate: %s (keep %s)",
                    path,
                    keep,
                )
                removed += 1
                continue
            try:
                path.unlink(missing_ok=True)
                removed += 1
                LOG.info(
                    "Removed lower-priority duplicate: %s (keep %s)",
                    path,
                    keep,
                )
            except OSError as exc:
                LOG.warning("Could not remove duplicate %s: %s", path, exc)

    return removed


def cleanup_preferred_jobs(jobs: Sequence[CsvJob], dry_run: bool = False) -> int:
    total = 0
    for job in jobs:
        total += cleanup_preferred_files(job.full_text_dir, dry_run=dry_run)
    return total


def append_failure(root: Path, task: PaperTask, reason: str) -> None:
    path = root / FAILURE_REPORT
    ensure_csv_utf8_sig(path)
    exists = path.exists() and path.stat().st_size > 0
    fields = ["time", "title", "journal_type", "sub_journal", "doi", "failure_reason", "csv_file"]
    with path.open("a", encoding=CSV_ENCODING, errors="strict", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(safe_csv_row({
            "time": datetime.now().isoformat(timespec="seconds"),
            "title": task.title,
            "journal_type": task.job.journal_type,
            "sub_journal": task.job.sub_journal,
            "doi": task.doi,
            "failure_reason": reason,
            "csv_file": str(task.job.csv_path),
        }))


def result_key_from_task(task: PaperTask) -> Tuple[str, str, str]:
    return (task.job.journal_type, task.job.sub_journal, task.doi)


def result_key_from_row(row: Dict[str, str]) -> Tuple[str, str, str]:
    return (row.get("journal_type", ""), row.get("sub_journal", ""), row.get("doi", ""))


def result_row(task: PaperTask, outcome: DownloadOutcome) -> Dict[str, str]:
    return safe_csv_row({
        "time": datetime.now().isoformat(timespec="seconds"),
        "title": task.title,
        "journal_type": task.job.journal_type,
        "sub_journal": task.job.sub_journal,
        "doi": task.doi,
        "status": outcome.status,
        "source": outcome.source,
        "file": outcome.file,
        "error": outcome.error,
        "csv_file": str(task.job.csv_path),
    })


def merge_result_row(existing_row: Dict[str, str], new_row: Dict[str, str]) -> Dict[str, str]:
    if existing_row.get("status") == "success" and new_row.get("status") == "failed":
        return existing_row
    if new_row.get("source") == "existing_pdf" and existing_row.get("source"):
        new_row["source"] = existing_row["source"]
    return new_row


def upsert_result(root: Path, task: PaperTask, outcome: DownloadOutcome) -> None:
    path = root / RESULT_REPORT
    ensure_csv_utf8_sig(path)
    fields = [
        "time", "title", "journal_type", "sub_journal", "doi",
        "status", "source", "file", "error", "csv_file",
    ]

    rows = read_rows(path) if path.exists() and path.stat().st_size > 0 else []
    new_row = result_row(task, outcome)
    target_key = result_key_from_task(task)
    replaced = False
    for index, row in enumerate(rows):
        if result_key_from_row(row) == target_key:
            rows[index] = merge_result_row(row, new_row)
            replaced = True
            break
    if not replaced:
        rows.append(new_row)

    with path.open("w", encoding=CSV_ENCODING, errors="strict", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(safe_csv_row({field: row.get(field, "") for field in fields}))


def append_result(root: Path, task: PaperTask, outcome: DownloadOutcome) -> None:
    upsert_result(root, task, outcome)


def load_processed(root: Path, retry_failed: bool) -> set[Tuple[str, str, str]]:
    path = root / RESULT_REPORT
    if not path.exists():
        return set()
    processed: set[Tuple[str, str, str]] = set()
    ensure_csv_utf8_sig(path)
    for row in read_rows(path):
        status = row.get("status", "")
        if retry_failed and status != "success":
            continue
        processed.add(result_key_from_row(row))
    return processed


def failed_result_keys(root: Path) -> set[Tuple[str, str, str]]:
    path = root / RESULT_REPORT
    if not path.exists():
        return set()
    ensure_csv_utf8_sig(path)
    return {
        result_key_from_row(row)
        for row in read_rows(path)
        if row.get("status") == "failed"
    }


def apply_existing_results(root: Path, stats: Dict[Tuple[str, str], Dict[str, int]]) -> None:
    path = root / RESULT_REPORT
    if not path.exists():
        return
    ensure_csv_utf8_sig(path)
    for row in read_rows(path):
        key = (row.get("journal_type", ""), row.get("sub_journal", ""))
        if key not in stats:
            continue
        stats[key]["processed_total"] += 1
        if row.get("status") == "success":
            stats[key]["download_success"] += 1
        else:
            stats[key]["download_failed"] += 1


def write_summary(root: Path, stats: Dict[Tuple[str, str], Dict[str, int]]) -> None:
    fields = [
        "journal_type", "sub_journal", "related_papers", "all_info_total",
        "download_success", "download_failed", "processed_total",
    ]
    path = root / SUMMARY_REPORT
    with path.open("w", encoding=CSV_ENCODING, errors="strict", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        total = {field: 0 for field in fields if field not in {"journal_type", "sub_journal"}}
        for (journal_type, sub_journal), item in sorted(stats.items()):
            row = {
                "journal_type": journal_type,
                "sub_journal": sub_journal,
                **item,
            }
            writer.writerow(safe_csv_row(row))
            for key in total:
                total[key] += int(row.get(key, 0))
        writer.writerow(safe_csv_row({"journal_type": "ALL", "sub_journal": "ALL", **total}))


class CombinedDownloader:
    def __init__(
        self,
        proxy: Optional[str],
        email: str,
        timeout: int,
        sources: Sequence[str],
        use_open_access: bool,
        use_scihub: bool,
        cookie_file: Optional[Path],
        limiters: DownloadLimiters,
        dynamic_cookie: bool = False,
    ) -> None:
        self.proxy = normalize_proxy(proxy)
        self.timeout = timeout
        self.sources = list(sources)
        self.email = email
        self.use_open_access = use_open_access
        self.use_scihub = use_scihub
        self.cookie_file = cookie_file
        self.dynamic_cookie = dynamic_cookie
        self.limiters = limiters

    def try_open_access(self, task: PaperTask) -> Optional[DownloadOutcome]:
        if not self.use_open_access:
            return None

        # If a PDF already exists, it is already the final winner.
        existing_pdf = existing_pdf_for_title(
            task.job.full_text_dir,
            task.title,
        )
        if existing_pdf:
            keep, _ = enforce_single_preferred_file(
                task.job.full_text_dir,
                task.title,
            )
            return DownloadOutcome(
                "skipped",
                source="existing_pdf",
                fmt="pdf",
                file=str(keep or existing_pdf),
            )

        downloader = RateLimitedDownloader(
            out_dir=task.job.full_text_dir,
            email=self.email,
            timeout=self.timeout,
            delay=(0, 0),
            overwrite=False,
            sources=self.sources,
            flat_output=True,
            limiters=self.limiters,
            proxy=self.proxy,
        )

        result: Result = downloader.one(task.doi, task.title)
        if result.status == "downloaded" and result.file:
            return DownloadOutcome(
                "success",
                source="open_access:" + result.source,
                fmt=result.fmt,
                file=result.file,
            )

        return DownloadOutcome(
            "failed",
            source="open_access",
            error=result.error or result.status,
        )

    def try_scihub(self, task: PaperTask) -> DownloadOutcome:
        if not self.use_scihub:
            return DownloadOutcome(
                "failed",
                source="scihub",
                error="Sci-Hub strategy disabled",
            )

        with self.limiters.scihub:
            return self._try_scihub_locked(task)

    def _try_scihub_locked(self, task: PaperTask) -> DownloadOutcome:
        task.job.full_text_dir.mkdir(parents=True, exist_ok=True)

        existing_pdf = existing_pdf_for_title(
            task.job.full_text_dir,
            task.title,
        )
        if existing_pdf:
            keep, _ = enforce_single_preferred_file(
                task.job.full_text_dir,
                task.title,
            )
            return DownloadOutcome(
                "skipped",
                source="existing_pdf",
                fmt="pdf",
                file=str(keep or existing_pdf),
            )

        sh = SciHub(proxy=self.proxy, dynamic_cookie=self.dynamic_cookie)
        sh.mirror_cookies = load_mirror_cookies(self.cookie_file)
        info = sh._get_paper_info(task.doi)
        if not info:
            return DownloadOutcome(
                "failed",
                source="scihub",
                error="No paper info found",
            )

        url = info.url
        response, diagnostics = sh.request_pdf_with_diagnostics(
            url,
            timeout=self.timeout,
        )

        content_type = response.headers.get("Content-Type", "").lower()
        if response.status_code != 200:
            return DownloadOutcome(
                "failed",
                source="scihub",
                error=(
                    f"PDF HTTP {response.status_code}; "
                    f"cookie_sent={diagnostics['cookie_sent']}; "
                    f"redirected={diagnostics['redirected']}; "
                    f"request_host={diagnostics['request_host']}; "
                    f"final_host={diagnostics['final_host']}; "
                    f"final_host_is_origin={diagnostics['final_host_is_origin']}; "
                    f"final_url={diagnostics['final_url']}; "
                    f"redirect_chain={diagnostics['redirect_chain']}"
                ),
            )

        if not (
            response.content.startswith(b"%PDF-")
            or "application/pdf" in content_type
        ):
            return DownloadOutcome(
                "failed",
                source="scihub",
                error=(
                    f"Non-PDF response: {content_type}; "
                    f"cookie_sent={diagnostics['cookie_sent']}; "
                    f"redirected={diagnostics['redirected']}; "
                    f"request_host={diagnostics['request_host']}; "
                    f"final_host={diagnostics['final_host']}; "
                    f"final_host_is_origin={diagnostics['final_host_is_origin']}; "
                    f"final_url={diagnostics['final_url']}; "
                    f"redirect_chain={diagnostics['redirect_chain']}"
                ),
            )

        title = task.title or info.title or task.doi
        target = (
            task.job.full_text_dir
            / f"{safe_name(title, 160)}.pdf"
        )

        if not target.exists():
            target.write_bytes(response.content)

        keep, _ = enforce_single_preferred_file(
            task.job.full_text_dir,
            title,
        )
        final_path = keep or target

        return DownloadOutcome(
            "success",
            source="scihub",
            fmt="pdf",
            file=str(final_path),
        )

    def convert_html_fallback_to_md(
        self,
        task: PaperTask,
        outcome: DownloadOutcome,
    ) -> DownloadOutcome:
        """
        HTML is not a final storage format. Landing/metadata HTML is never converted to Markdown.

        When HTML is the only usable fallback:
            HTML -> readable Markdown -> delete HTML

        This preserves the final one-file rule.
        """
        if outcome.fmt != "html" or not outcome.file:
            return outcome

        html_path = Path(outcome.file)
        if not html_path.exists():
            return DownloadOutcome(
                "failed",
                source=outcome.source,
                error=f"HTML fallback file does not exist: {html_path}",
            )

        validator = RateLimitedDownloader(
            out_dir=task.job.full_text_dir,
            email=self.email,
            timeout=self.timeout,
            delay=(0, 0),
            overwrite=False,
            sources=[],
            flat_output=True,
            limiters=self.limiters,
            proxy=self.proxy,
        )

        result = Result(
            "downloaded",
            fmt="html",
            file=str(html_path),
            source=outcome.source,
        )

        try:
            raw_html = html_path.read_text(encoding="utf-8", errors="ignore")
            page_type = validator.classify_html_page(raw_html)
        except Exception as exc:
            return DownloadOutcome(
                "failed",
                source=outcome.source,
                error=f"HTML classification failed: {exc}",
            )

        if page_type != "fulltext":
            try:
                html_path.unlink(missing_ok=True)
            except OSError:
                pass
            return DownloadOutcome(
                "failed",
                source=outcome.source,
                error=(
                    "HTML不是文章全文页，已删除临时HTML "
                    f"(classification={page_type})"
                ),
            )

        if not validator.validate_fulltext_file(result):
            return DownloadOutcome(
                "failed",
                source=outcome.source,
                error=(
                    "HTML fallback did not pass full-text validation: "
                    f"{html_path}"
                ),
            )

        try:
            markdown = validator.html_to_markdown(
                html_path,
                task.title,
            )
        except Exception as exc:
            return DownloadOutcome(
                "failed",
                source=outcome.source,
                error=f"HTML to Markdown conversion failed: {exc}",
            )

        md_path = (
            task.job.full_text_dir
            / f"{safe_name(task.title or html_path.stem, 160)}.md"
        )
        if not md_path.exists():
            md_path.write_text(markdown, encoding="utf-8")

        try:
            html_path.unlink(missing_ok=True)
        except OSError as exc:
            LOG.warning(
                "Could not remove HTML after Markdown conversion %s: %s",
                html_path,
                exc,
            )

        keep, _ = enforce_single_preferred_file(
            task.job.full_text_dir,
            task.title,
        )
        final_path = keep or md_path

        LOG.info(
            "Converted HTML fallback to Markdown: %s",
            final_path,
        )
        return DownloadOutcome(
            "success",
            source=outcome.source + ":md_fallback",
            fmt=final_path.suffix.lower().lstrip("."),
            file=str(final_path),
        )

    def finalize_single_file(
        self,
        task: PaperTask,
        outcome: DownloadOutcome,
    ) -> DownloadOutcome:
        """
        Collapse all same-title full-text artifacts to exactly one file.

        Final priority:
            PDF > XML > JSON > MD
        """
        if outcome.status != "success":
            return outcome

        keep, removed = enforce_single_preferred_file(
            task.job.full_text_dir,
            task.title,
        )
        if not keep:
            LOG.warning(
                "Finalization found no matching same-title files: title=%r key=%r dir=%s",
                task.title,
                title_key(task.title),
                task.job.full_text_dir,
            )
            return outcome

        if removed:
            LOG.info(
                "Finalized %s: removed %d lower-priority duplicate(s), kept %s",
                task.title,
                removed,
                keep,
            )

        return DownloadOutcome(
            "success",
            source=outcome.source,
            fmt=keep.suffix.lower().lstrip("."),
            file=str(keep),
            error=outcome.error,
        )

    def download(self, task: PaperTask) -> DownloadOutcome:
        """
        Download one paper and leave exactly one final file.

        Final preference:
            PDF > XML > JSON > MD

        Strategy:
        1. Open-access sources first.
        2. If OA already returned PDF -> finish.
        3. If OA returned XML/JSON/HTML -> keep as fallback,
           but still try Sci-Hub for PDF.
        4. If Sci-Hub gets PDF -> PDF wins and all lower formats are removed.
        5. If no PDF:
             XML wins over JSON/MD;
             JSON wins over MD;
             HTML is converted to Markdown.
        """
        existing_pdf = existing_pdf_for_title(
            task.job.full_text_dir,
            task.title,
        )
        if existing_pdf:
            keep, _ = enforce_single_preferred_file(
                task.job.full_text_dir,
                task.title,
            )
            return DownloadOutcome(
                "skipped",
                source="existing_pdf",
                fmt="pdf",
                file=str(keep or existing_pdf),
            )

        errors: List[str] = []
        fallback_result: Optional[DownloadOutcome] = None

        open_result = self.try_open_access(task)
        if open_result and open_result.status == "success":
            if open_result.fmt == "pdf":
                return self.finalize_single_file(task, open_result)

            fallback_result = open_result
            LOG.info(
                "Open-access full text is %s; trying Sci-Hub for PDF before fallback.",
                open_result.fmt,
            )
        elif open_result:
            errors.append(open_result.error)

        try:
            sci_result = self.try_scihub(task)
            if sci_result.status == "success":
                return self.finalize_single_file(task, sci_result)
            errors.append(sci_result.error)
        except Exception as exc:
            errors.append(f"scihub: {exc}")

        if fallback_result:
            if fallback_result.fmt == "html":
                fallback_result = self.convert_html_fallback_to_md(
                    task,
                    fallback_result,
                )
                if fallback_result.status != "success":
                    errors.append(fallback_result.error)
                    return DownloadOutcome(
                        "failed",
                        source="combined",
                        error=" | ".join(x for x in errors if x),
                    )

            return self.finalize_single_file(
                task,
                fallback_result,
            )

        # It is possible that Downloader.one() downloaded multiple valid
        # non-PDF files while searching but returned none due to a source error.
        # Recover the highest-priority existing final-format file if present.
        existing = preferred_existing_file(
            task.job.full_text_dir,
            task.title,
        )
        if existing:
            recovered = DownloadOutcome(
                "success",
                source="existing_recovered",
                fmt=existing.suffix.lower().lstrip("."),
                file=str(existing),
            )
            return self.finalize_single_file(task, recovered)

        return DownloadOutcome(
            "failed",
            source="combined",
            error=" | ".join(x for x in errors if x),
        )


def parse_sources(value: str) -> List[str]:
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    invalid = [item for item in items if item not in DEFAULT_SOURCES]
    if invalid:
        raise argparse.ArgumentTypeError("Unknown source(s): " + ",".join(invalid))
    return items or list(DEFAULT_SOURCES)


def parse_bool(value: str) -> bool:
    value = str(value).strip().lower()
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("Boolean value must be true or false")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch download sleep-related full text by journal/sub-journal.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--batch-size", type=int, default=0, help="Number of papers to process. Use 0 to process all remaining papers.")
    parser.add_argument("--workers", type=int, default=5, help="Total concurrent download tasks.")
    parser.add_argument("--scihub-workers", type=int, default=1, help="Concurrent Sci-Hub tasks. Use 1 for best cookie/challenge stability.")
    parser.add_argument("--semantic-scholar-interval", type=float, default=5.0, help="Minimum seconds between Semantic Scholar requests.")
    parser.add_argument("--crossref-interval", type=float, default=1.0, help="Minimum seconds between Crossref requests.")
    parser.add_argument("--unpaywall-interval", type=float, default=1.0, help="Minimum seconds between Unpaywall requests.")
    parser.add_argument("--openalex-interval", type=float, default=1.0, help="Minimum seconds between OpenAlex requests.")
    parser.add_argument("--pubmed-interval", type=float, default=1.0, help="Minimum seconds between PubMed requests.")
    parser.add_argument("--europe-pmc-interval", type=float, default=1.0, help="Minimum seconds between Europe PMC requests.")
    parser.add_argument("--pmc-interval", type=float, default=1.0, help="Minimum seconds between PMC requests.")
    parser.add_argument("--publisher-host-workers", type=int, default=1, help="Concurrent direct publisher PDF requests per host.")
    parser.add_argument("--proxy", default="http://127.0.0.1:7890")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--cookie-file", type=Path, default=DEFAULT_COOKIE_FILE)
    parser.add_argument("--dynamic-cookie", type=parse_bool, default=False, help="Refresh cf_clearance with curl_cffi when blocked; keep static cookie-file values as fallback.")
    parser.add_argument("--sources", type=parse_sources, default=list(DEFAULT_SOURCES))
    parser.add_argument("--skip-open-access", type=parse_bool, default=False)
    parser.add_argument("--skip-scihub", type=parse_bool, default=False)
    parser.add_argument("--no-resume", type=parse_bool, default=False, help="Do not skip rows already listed in download_results.csv.")
    parser.add_argument("--retry-failed", type=parse_bool, default=True, help="When resuming, retry previous failures.")
    parser.add_argument("--cleanup-only", type=parse_bool, default=False, help="Only clean duplicate full-text files using PDF > XML > JSON > MD priority.")
    parser.add_argument("--dry-run", type=parse_bool, default=False, help="List selected DOI tasks without downloading or writing reports.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", force=True)
    if args.batch_size < 0:
        raise SystemExit("--batch-size must be 0 or positive")
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    if args.scihub_workers < 1:
        raise SystemExit("--scihub-workers must be at least 1")
    if args.publisher_host_workers < 1:
        raise SystemExit("--publisher-host-workers must be at least 1")
    jobs = discover_jobs(args.root)
    if not jobs:
        raise SystemExit(f"No sleep_related_*.csv files found under {args.root}")

    if args.cleanup_only:
        removed = cleanup_preferred_jobs(jobs, dry_run=args.dry_run)
        action = "Would remove" if args.dry_run else "Removed"
        LOG.info("%s %d lower-priority duplicate file(s) using PDF > XML > JSON > MD.", action, removed)
        return 0

    stats: Dict[Tuple[str, str], Dict[str, int]] = {}
    for job in jobs:
        key = (job.journal_type, job.sub_journal)
        stats[key] = {
            "related_papers": count_csv_rows(job.csv_path),
            "all_info_total": count_csv_rows(job.all_info_path),
            "download_success": 0,
            "download_failed": 0,
            "processed_total": 0,
        }
    apply_existing_results(args.root, stats)

    previous_failed = failed_result_keys(args.root) if args.retry_failed else set()
    processed = set() if args.no_resume else load_processed(args.root, args.retry_failed)
    all_tasks = list(iter_tasks(jobs))
    tasks = [
        task for task in iter_tasks(jobs)
        if (task.job.journal_type, task.job.sub_journal, task.doi) not in processed
    ]
    max_items = len(tasks) if args.batch_size == 0 else args.batch_size
    selected = tasks[:max_items]
    LOG.info(
        "Discovered %d CSV files and %d total DOI tasks. Resume skipped %d processed task(s); %d task(s) remain. Processing %d task(s).",
        len(jobs), len(all_tasks), len(all_tasks) - len(tasks), len(tasks), len(selected),
    )
    if args.dry_run:
        for index, task in enumerate(selected, 1):
            LOG.info(
                "[dry-run %d/%d] %s / %s | %s | %s",
                index, len(selected), task.job.journal_type, task.job.sub_journal, task.doi, task.title,
            )
        removed = cleanup_preferred_jobs(jobs, dry_run=True)
        LOG.info("Dry-run cleanup would remove %d lower-priority duplicate file(s) using PDF > XML > JSON > MD.", removed)
        return 0

    limiters = DownloadLimiters(
        scihub_workers=args.scihub_workers,
        semantic_interval=args.semantic_scholar_interval,
        crossref_interval=args.crossref_interval,
        unpaywall_interval=args.unpaywall_interval,
        openalex_interval=args.openalex_interval,
        pubmed_interval=args.pubmed_interval,
        europe_pmc_interval=args.europe_pmc_interval,
        pmc_interval=args.pmc_interval,
        publisher_host_workers=args.publisher_host_workers,
    )

    downloader = CombinedDownloader(
        proxy=args.proxy,
        email=args.email,
        timeout=args.timeout,
        sources=args.sources,
        use_open_access=not args.skip_open_access,
        use_scihub=not args.skip_scihub,
        cookie_file=args.cookie_file,
        limiters=limiters,
        dynamic_cookie=args.dynamic_cookie,
    )

    def run_task(index_task: Tuple[int, PaperTask]) -> Tuple[int, PaperTask, DownloadOutcome]:
        index, task = index_task
        task_key = result_key_from_task(task)
        retry_note = " | retrying previous failed" if task_key in previous_failed else ""
        LOG.info(
            "[%d/%d] started | %s / %s | %s%s",
            index,
            len(selected),
            task.job.journal_type,
            task.job.sub_journal,
            task.doi,
            retry_note,
        )
        outcome = downloader.download(task)
        return index, task, outcome

    indexed_selected = list(enumerate(selected, 1))
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_task, item): item
            for item in indexed_selected
        }
        for future in as_completed(futures):
            submitted_index, submitted_task = futures[future]
            try:
                index, task, outcome = future.result()
            except Exception as exc:
                index, task = submitted_index, submitted_task
                outcome = DownloadOutcome(
                    "failed",
                    source="threaded",
                    error=f"Worker exception: {exc}",
                )
            key = (task.job.journal_type, task.job.sub_journal)
            LOG.info(
                "[%d/%d] completed | %s / %s | %s | %s",
                index,
                len(selected),
                task.job.journal_type,
                task.job.sub_journal,
                task.doi,
                outcome.status,
            )
            if outcome.status == "skipped":
                LOG.info("Skipped existing PDF: %s", outcome.file)
                continue
            stats[key]["processed_total"] += 1
            if outcome.status == "success":
                stats[key]["download_success"] += 1
                LOG.info("Downloaded via %s: %s", outcome.source, outcome.file)
            else:
                stats[key]["download_failed"] += 1
                append_failure(args.root, task, outcome.error)
                LOG.error("Failed: %s", outcome.error)
            upsert_result(args.root, task, outcome)
            write_summary(args.root, stats)

    write_summary(args.root, stats)
    totals = {}
    for item in stats.values():
        for key, value in item.items():
            totals[key] = totals.get(key, 0) + value
    LOG.info("Summary: %s", json.dumps(totals, ensure_ascii=False))
    LOG.info("Failure report: %s", args.root / FAILURE_REPORT)
    LOG.info("Result report: %s", args.root / RESULT_REPORT)
    LOG.info("Summary report: %s", args.root / SUMMARY_REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
