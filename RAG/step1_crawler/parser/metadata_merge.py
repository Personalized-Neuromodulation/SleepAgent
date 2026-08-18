# -*- coding: utf-8 -*-
import re
from datetime import date, datetime

from crawl_checkpoint import normalize_doi
from parser.text_cleanup import clean_metadata_text


FILL_FIELDS = (
    "title",
    "date",
    "doi",
    "link",
    "url",
    "authors",
    "journal",
    "article_type",
    "type",
    "issue",
    "quality_score",
)


def metadata_key(row):
    row = row or {}
    doi = normalize_doi(row.get("doi") or row.get("link") or row.get("url"))
    if doi:
        return "doi:" + doi.lower()

    title = _normalize_title(row.get("title"))
    if not title:
        return ""

    year = _year(row.get("date"))
    journal = _normalize_title(row.get("journal"))
    return "title:%s|%s|%s" % (title, year, journal)


def merge_metadata_rows(existing_rows, incoming_rows):
    rows = []
    index_by_key = {}

    for row in existing_rows or []:
        item = dict(row or {})
        key = metadata_key(item)
        if key and key in index_by_key:
            rows[index_by_key[key]] = merge_metadata_pair(rows[index_by_key[key]], item)
            continue
        if key:
            index_by_key[key] = len(rows)
        rows.append(item)

    for row in incoming_rows or []:
        item = dict(row or {})
        key = metadata_key(item)
        if key and key in index_by_key:
            rows[index_by_key[key]] = merge_metadata_pair(rows[index_by_key[key]], item)
            continue
        if key:
            index_by_key[key] = len(rows)
        rows.append(item)

    return rows


def merge_metadata_pair(existing, incoming):
    result = dict(existing or {})
    incoming = dict(incoming or {})

    if _better_text(incoming.get("abstract"), result.get("abstract")):
        result["abstract"] = clean_metadata_text(incoming.get("abstract"))

    for field in FILL_FIELDS:
        current = result.get(field)
        value = incoming.get(field)
        if _has_value(current):
            continue
        if field == "link" and not _has_value(value):
            value = incoming.get("url")
        elif field == "url" and not _has_value(value):
            value = incoming.get("link")
        if _has_value(value):
            result[field] = _stringify(value)

    source = _merge_sources(result.get("source"), incoming.get("source"))
    if source:
        result["source"] = source

    metadata_sources = _merge_sources(result.get("metadata_sources"), incoming.get("metadata_sources"))
    if source:
        metadata_sources = _merge_sources(metadata_sources, source)
    if metadata_sources:
        result["metadata_sources"] = metadata_sources

    return result


def _better_text(candidate, current):
    candidate_text = clean_metadata_text(candidate)
    current_text = clean_metadata_text(current)
    return bool(candidate_text) and len(candidate_text) > len(current_text)


def _has_value(value):
    text = str(value or "").strip()
    return bool(text) and text.lower() != "nan"


def _stringify(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _normalize_title(value):
    text = clean_metadata_text(value).lower()
    return re.sub(r"\s+", " ", text).strip()


def _year(value):
    if isinstance(value, datetime):
        return str(value.year)
    if isinstance(value, date):
        return str(value.year)
    match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    return match.group(0) if match else ""


def _merge_sources(*values):
    result = []
    seen = set()
    for value in values:
        for part in re.split(r"[;,|]+", str(value or "")):
            item = part.strip()
            key = item.lower()
            if not item or key in seen:
                continue
            seen.add(key)
            result.append(item)
    return ";".join(result)
