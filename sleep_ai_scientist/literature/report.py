from __future__ import annotations

from pathlib import Path
from typing import Any


def build_library_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Sleep Literature Library Build Report",
        "",
        f"- Library version: {summary.get('library_version', '')}",
        f"- Query set version: {summary.get('query_set_version', '')}",
        f"- API papers: {summary.get('api_papers', 0)}",
        f"- Registry records: {summary.get('registry_records', 0)}",
        f"- Duplicate groups: {summary.get('duplicate_groups', 0)}",
        f"- Coverage audit: {summary.get('coverage_audit', '')}",
        f"- Anchor papers: {summary.get('anchor_papers', '')}",
        f"- Query expansion candidates: {summary.get('query_expansion_candidates', '')}",
        f"- Manifest: {summary.get('manifest', '')}",
        "",
        "## Provider Summary",
        "",
        f"{summary.get('provider_summary', {})}",
        "",
        "## Warnings",
        "",
    ]
    warnings = summary.get("warnings", [])
    lines.extend([f"- {item}" for item in warnings] if warnings else ["- none"])
    lines.append("")
    return "\n".join(lines)


def write_library_report(path: str | Path, report: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
