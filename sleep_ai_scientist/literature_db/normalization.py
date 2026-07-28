from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime


def normalize_doi(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    text = re.sub(r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", "", text)
    text = text.rstrip(".,;:)]}>").strip()
    return text or None


def normalize_pmid(value: str | None) -> str | None:
    text = re.sub(r"^pmid\s*:\s*", "", (value or "").strip(), flags=re.I).replace(" ", "")
    return text if text.isdigit() else None


def normalize_pmcid(value: str | None) -> str | None:
    text = re.sub(r"[\s:_-]", "", (value or "").upper())
    text = text[3:] if text.startswith("PMC") else text
    return f"PMC{text}" if text.isdigit() else None


def normalize_title(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = re.sub(r"[^\w\sα-ωΑ-Ω-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_journal(value: str | None) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "").casefold()).strip(" .")


def normalize_author(value: str | None) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "").casefold().replace(",", " ")).strip()


def normalize_issn(value: str | None) -> str | None:
    text = re.sub(r"[^0-9Xx]", "", value or "").upper()
    return f"{text[:4]}-{text[4:]}" if len(text) == 8 else None


def normalize_date(value: str | date | datetime | None) -> date | None:
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y", "%Y/%m/%d"):
        try: return datetime.strptime(text, fmt).date()
        except ValueError: pass
    return None
