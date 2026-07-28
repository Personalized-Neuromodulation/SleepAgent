from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--output-dir", default="reports/literature/journal_crawl")
    args = parser.parse_args()

    rows = {}
    for report_path in args.reports:
        payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
        rows.update({row["journal_key"]: row for row in payload["per_journal_results"]})
    journals = list(rows.values())
    status = Counter(row["status"] for row in journals)
    form_status = Counter(row.get("search_form_status") for row in journals)
    summary = {
        "unique_target_journals": len(journals),
        "html_pages_parsed": sum(row.get("html_page_status") == "parsed" for row in journals),
        "search_forms_present": sum(bool(row.get("search_form")) for row in journals),
        "searches_submitted": sum(bool(row.get("search_queries_attempted")) for row in journals),
        "searches_with_result_links": sum(row.get("search_form_status") == "searched_with_results" for row in journals),
        "journals_with_papers_parsed_from_search": sum(row.get("articles_parsed_from_search", 0) > 0 for row in journals),
        "papers_parsed_from_search": sum(row.get("articles_parsed_from_search", 0) for row in journals),
        "api_fallback_samples": sum(row.get("sample_discovery_channel") == "api_fallback" for row in journals),
        "status_breakdown": dict(status),
        "search_form_status_breakdown": dict(form_status),
    }
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_reports": args.reports,
        "summary": summary,
        "per_journal_results": journals,
    }
    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = payload["timestamp"].replace("-", "").replace(":", "").split(".")[0] + "Z"
    json_path = root / f"{stamp}_web_search_audit.json"
    markdown_path = root / f"{stamp}_web_search_audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = [
        "# Target Journal Web Search Audit",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "```",
        "",
        "| Journal | Homepage | HTML | Search form | Queries | Search papers | Status | Error |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    for row in journals:
        error = (row.get("error") or {}).get("message", "").replace("|", "\\|")
        lines.append(
            f"| {row.get('journal','')} | {row.get('official_url','')} | "
            f"{row.get('html_page_status','')} | {row.get('search_form_status','')} | "
            f"{', '.join(row.get('search_queries_attempted') or [])} | "
            f"{row.get('articles_parsed_from_search',0)} | {row.get('status','')} | {error} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "json": str(json_path), "markdown": str(markdown_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
