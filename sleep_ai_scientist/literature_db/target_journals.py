from __future__ import annotations

import csv, hashlib, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .normalization import normalize_issn, normalize_journal


class TargetJournalSchemaError(ValueError): pass


ALIASES = {
    "title": {"journal", "journal name", "journal title", "full journal title", "title", "journal name full", "期刊名称"},
    "issn": {"issn", "print issn", "pissn", "issn print"},
    "eissn": {"eissn", "electronic issn", "online issn", "issn online"},
    "publisher": {"publisher", "publisher name", "出版社"},
    "impact_factor": {"impact factor", "journal impact factor", "jif", "if", "2025 jif", "影响因子"},
    "quartile": {"quartile", "jcr quartile", "jif quartile", "q", "分区"},
    "official_url": {"official url", "journal url", "url", "期刊url", "期刊网址", "官方网站"},
    "url_validation_status": {"url validation status", "url status", "url校验状态"},
    "url_review_reason": {"url review reason", "url审核原因"},
}


def _header(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.lstrip("\ufeff").strip().casefold())


@dataclass
class TargetJournal:
    journal_key: str; title: str; normalized_title: str; issn: str | None = None; eissn: str | None = None
    publisher: str | None = None; impact_factor: str | None = None; quartile: str | None = None; identifier_quality: str = "title_only"
    source_row_numbers: list[int] = field(default_factory=list); raw_records: list[dict[str, Any]] = field(default_factory=list); warnings: list[str] = field(default_factory=list)
    official_url: str | None = None; url_validation_status: str | None = None; url_review_reason: str | None = None


class TargetJournalLoader:
    def __init__(self, path: str | Path): self.path = Path(path); self.stats: dict[str, Any] = {}; self.errors: list[str] = []; self.warnings: list[str] = []

    def load(self) -> list[TargetJournal]:
        if not self.path.exists(): raise FileNotFoundError(f"Target journal file not found: {self.path}")
        raw = self.path.read_bytes(); encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        text = raw.decode(encoding); dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        reader = csv.DictReader(text.splitlines(), dialect=dialect); headers = reader.fieldnames or []
        mapped = self._map_headers(headers)
        if "title" not in mapped:
            supported = sorted(ALIASES["title"])
            raise TargetJournalSchemaError(f"Target journal schema error in {self.path}; actual columns={headers}; supported journal-title columns={supported}. Rename the journal title column to a supported name.")
        rows = list(reader); valid: list[TargetJournal] = []; missing_both = invalid = 0
        for rowno, row in enumerate(rows, 2):
            title = str(row.get(mapped["title"], "") or "").strip()
            if not title: invalid += 1; self.errors.append(f"row {rowno}: missing journal title"); continue
            issn = normalize_issn(row.get(mapped.get("issn", ""))); eissn = normalize_issn(row.get(mapped.get("eissn", "")))
            if not issn and not eissn: missing_both += 1
            norm = normalize_journal(title); basis = issn or eissn or norm
            key = "journal:" + hashlib.sha256(basis.encode()).hexdigest()[:24]
            quality = "issn_and_eissn" if issn and eissn else "issn_only" if issn else "eissn_only" if eissn else "title_only"
            def val(name): return str(row.get(mapped.get(name, ""), "") or "").strip() or None
            item=TargetJournal(key, title, norm, issn, eissn, val("publisher"), val("impact_factor"), val("quartile"), quality, [rowno], [dict(row)])
            item.official_url=val("official_url");item.url_validation_status=val("url_validation_status");item.url_review_reason=val("url_review_reason");valid.append(item)
        merged = self._deduplicate(valid)
        self.stats = {"path": str(self.path), "encoding": encoding, "utf8_bom": raw.startswith(b"\xef\xbb\xbf"), "delimiter": dialect.delimiter, "detected_columns": headers, "mapped_columns": mapped, "row_count": len(rows), "empty_rows": sum(not any(str(v or '').strip() for v in r.values()) for r in rows), "valid_journal_rows": len(valid), "normalized_journal_count": len(merged), "duplicate_rows_merged": len(valid)-len(merged), "rows_missing_journal_title": invalid, "rows_missing_both_issn_eissn": missing_both, "warnings": self.warnings, "errors": self.errors}
        return merged

    def _map_headers(self, headers: list[str]) -> dict[str, str]:
        lookup = {_header(h): h for h in headers}; result = {}
        for field, aliases in ALIASES.items():
            for alias in aliases:
                if _header(alias) in lookup: result[field] = lookup[_header(alias)]; break
        return result

    def _deduplicate(self, journals: list[TargetJournal]) -> list[TargetJournal]:
        groups: list[TargetJournal] = []
        for item in journals:
            match = next((x for x in groups if ({item.issn,item.eissn}-{None}) & ({x.issn,x.eissn}-{None}) or item.normalized_title == x.normalized_title), None)
            if not match: groups.append(item); continue
            if ({item.issn,item.eissn}-{None}) & ({match.issn,match.eissn}-{None}) and item.normalized_title != match.normalized_title:
                warning=f"journal_identifier_conflict: {match.title!r} vs {item.title!r}"; self.warnings.append(warning); match.warnings.append(warning)
            match.source_row_numbers.extend(item.source_row_numbers); match.raw_records.extend(item.raw_records)
            match.issn = match.issn or item.issn; match.eissn = match.eissn or item.eissn; match.publisher = match.publisher or item.publisher; match.impact_factor = match.impact_factor or item.impact_factor; match.quartile = match.quartile or item.quartile
            match.official_url = match.official_url or item.official_url; match.url_validation_status = match.url_validation_status or item.url_validation_status; match.url_review_reason = match.url_review_reason or item.url_review_reason
            match.identifier_quality = "issn_and_eissn" if match.issn and match.eissn else "issn_only" if match.issn else "eissn_only" if match.eissn else "title_only"
        return sorted(groups, key=lambda x: x.journal_key)
