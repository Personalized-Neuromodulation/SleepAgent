import csv
import sys
from pathlib import Path

from batch_download_sleep_fulltext import (
    CsvJob,
    CombinedDownloader,
    DownloadOutcome,
    FINAL_FORMAT_PRIORITY,
    PaperTask,
    RESULT_REPORT,
    enforce_single_preferred_file,
    failed_result_keys,
    main,
    upsert_result,
)
from download import Downloader, normalize_proxy
from batch_download_sleep_fulltext_threaded import FINAL_FORMAT_PRIORITY as THREADED_FINAL_FORMAT_PRIORITY


def make_task(tmp_path, doi="10.1000/example"):
    job = CsvJob(
        csv_path=tmp_path / "sleep_related.csv",
        journal_type="nature",
        sub_journal="MOLECULAR PSYCHIATRY",
        full_text_dir=tmp_path / "full_text",
        all_info_path=tmp_path / "all_info.csv",
    )
    return PaperTask(job=job, row={}, doi=doi, title="Example Paper")


def read_result_rows(root):
    with (root / RESULT_REPORT).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_normalize_proxy_accepts_common_cli_values():
    assert normalize_proxy(None) is None
    assert normalize_proxy("") is None
    assert normalize_proxy("none") is None
    assert normalize_proxy("direct") is None
    assert normalize_proxy("127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert normalize_proxy("socks5://127.0.0.1:10808") == "socks5h://127.0.0.1:10808"
    assert normalize_proxy("socks5h://127.0.0.1:10808") == "socks5h://127.0.0.1:10808"


def test_downloader_uses_explicit_proxy_and_ignores_environment_proxies(tmp_path):
    downloader = Downloader(
        out_dir=tmp_path,
        email="test@example.com",
        proxy="127.0.0.1:7890",
    )

    assert downloader.proxy == "http://127.0.0.1:7890"
    assert downloader.session.trust_env is False
    assert downloader.session.proxies == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_combined_downloader_normalizes_proxy_once():
    downloader = CombinedDownloader(
        proxy="socks5://127.0.0.1:10808",
        email="test@example.com",
        timeout=45,
        sources=[],
        use_open_access=True,
        use_scihub=True,
        cookie_file=None,
    )

    assert downloader.proxy == "socks5h://127.0.0.1:10808"


def test_final_format_priority_uses_markdown_and_removes_legacy_txt(tmp_path):
    assert FINAL_FORMAT_PRIORITY == {".pdf": 0, ".xml": 1, ".json": 2, ".md": 3}
    assert THREADED_FINAL_FORMAT_PRIORITY == FINAL_FORMAT_PRIORITY

    full_text_dir = tmp_path / "full_text"
    full_text_dir.mkdir()
    markdown = full_text_dir / "Example Paper.md"
    legacy_txt = full_text_dir / "Example Paper.txt"
    markdown.write_text("# Example Paper\n\nFull text", encoding="utf-8")
    legacy_txt.write_text("legacy", encoding="utf-8")

    keep, removed = enforce_single_preferred_file(full_text_dir, "Example Paper")

    assert keep == markdown
    assert removed == 1
    assert not legacy_txt.exists()


def test_html_fallback_is_converted_to_markdown_only(tmp_path):
    task = make_task(tmp_path)
    task.job.full_text_dir.mkdir(parents=True)
    html_path = task.job.full_text_dir / "Example Paper.html"
    sections = []
    for name in ("Abstract", "Introduction", "Methods", "Results", "Discussion", "References"):
        paragraphs = "".join(
            f"<p>{name} paragraph {i}. Detailed sleep physiology, experimental methods, "
            "results, interpretation, and supporting evidence are described here.</p>"
            for i in range(15)
        )
        sections.append(f"<section><h2>{name}</h2>{paragraphs}</section>")
    html_path.write_text(f"<html><body><article>{''.join(sections)}</article></body></html>", encoding="utf-8")
    downloader = CombinedDownloader(
        proxy=None,
        email="test@example.com",
        timeout=45,
        sources=[],
        use_open_access=True,
        use_scihub=False,
        cookie_file=None,
    )

    result = downloader.convert_html_fallback_to_md(
        task,
        DownloadOutcome("success", source="open_access:OpenAlex", fmt="html", file=str(html_path)),
    )

    assert result.status == "success"
    assert result.fmt == "md"
    assert result.source.endswith(":md_fallback")
    assert Path(result.file).suffix == ".md"
    assert Path(result.file).exists()
    assert "## Abstract" in Path(result.file).read_text(encoding="utf-8")
    assert not html_path.exists()
    assert not list(task.job.full_text_dir.glob("*.txt"))


def test_upsert_result_replaces_previous_failed_row_for_same_task(tmp_path):
    task = make_task(tmp_path)

    upsert_result(
        tmp_path,
        task,
        DownloadOutcome("failed", source="combined", error="old failure"),
    )
    upsert_result(
        tmp_path,
        task,
        DownloadOutcome("success", source="scihub", fmt="pdf", file="paper.pdf"),
    )

    rows = read_result_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["source"] == "scihub"
    assert rows[0]["file"] == "paper.pdf"
    assert rows[0]["error"] == ""


def test_upsert_result_preserves_source_when_existing_pdf_is_reused(tmp_path):
    task = make_task(tmp_path)

    upsert_result(
        tmp_path,
        task,
        DownloadOutcome("success", source="scihub", fmt="pdf", file="paper.pdf"),
    )
    upsert_result(
        tmp_path,
        task,
        DownloadOutcome("success", source="existing_pdf", fmt="pdf", file="paper.pdf"),
    )

    rows = read_result_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["source"] == "scihub"
    assert rows[0]["file"] == "paper.pdf"


def test_upsert_result_does_not_downgrade_previous_success_to_failed(tmp_path):
    task = make_task(tmp_path)

    upsert_result(
        tmp_path,
        task,
        DownloadOutcome("success", source="scihub", fmt="pdf", file="paper.pdf"),
    )
    upsert_result(
        tmp_path,
        task,
        DownloadOutcome("failed", source="combined", error="network failed"),
    )

    rows = read_result_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["source"] == "scihub"
    assert rows[0]["file"] == "paper.pdf"
    assert rows[0]["error"] == ""


def test_main_skips_existing_pdf_after_cleaning_lower_priority_fallbacks(monkeypatch, tmp_path):
    job_dir = tmp_path / "nature" / "MOLECULAR PSYCHIATRY"
    full_text_dir = job_dir / "full_text"
    full_text_dir.mkdir(parents=True)
    (job_dir / "sleep_related_test.csv").write_text(
        "doi,title\n10.1000/example,Example Paper\n",
        encoding="utf-8",
    )
    (job_dir / "all_info.csv").write_text(
        "doi,title\n10.1000/example,Example Paper\n",
        encoding="utf-8",
    )
    (full_text_dir / "Example Paper.pdf").write_bytes(b"%PDF-1.4")
    fallback = full_text_dir / "Example Paper.xml"
    fallback.write_text("<article />", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_download_sleep_fulltext.py",
            "--root",
            str(tmp_path),
            "--batch-size",
            "0",
        ],
    )

    assert main() == 0
    assert not fallback.exists()
    assert not (tmp_path / RESULT_REPORT).exists()


def test_failed_result_keys_returns_only_latest_failed_rows(tmp_path):
    failed_task = make_task(tmp_path, doi="10.1000/failed")
    recovered_task = make_task(tmp_path, doi="10.1000/recovered")

    upsert_result(
        tmp_path,
        failed_task,
        DownloadOutcome("failed", source="combined", error="still failed"),
    )
    upsert_result(
        tmp_path,
        recovered_task,
        DownloadOutcome("failed", source="combined", error="old failure"),
    )
    upsert_result(
        tmp_path,
        recovered_task,
        DownloadOutcome("success", source="scihub", fmt="pdf", file="paper.pdf"),
    )

    assert failed_result_keys(tmp_path) == {
        ("nature", "MOLECULAR PSYCHIATRY", "10.1000/failed")
    }
