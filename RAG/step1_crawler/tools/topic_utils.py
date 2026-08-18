import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import urlparse
from urllib.parse import urlunparse


PLATFORM_FAMILIES = ("nature", "science", "cell", "plos", "other")

@dataclass(frozen=True)
class TopicConfig:
    name: str
    keywords: List[str]


def safe_path_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name).strip())
    cleaned = cleaned.rstrip(". ")
    return cleaned or "unknown_journal"


def article_matches_topic(article: dict, topic: TopicConfig) -> bool:
    haystack = f"{article.get('title', '')} {article.get('abstract', '')}".lower()
    for keyword in topic.keywords:
        value = str(keyword or "").strip().lower()
        if not value:
            continue
        pattern = r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(value)
        if re.search(pattern, haystack):
            return True
    return False


def build_search_keywords(topic: TopicConfig) -> List[str]:
    source = topic.keywords
    seen = set()
    result = []
    for keyword in source:
        value = str(keyword).strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def normalize_candidate_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    path = parsed.path.rstrip("/")
    host = parsed.netloc.lower()
    return urlunparse((parsed.scheme.lower(), host, path, "", parsed.query, ""))


def dedupe_candidate_urls(candidates: Iterable[dict]) -> List[dict]:
    seen = set()
    result = []
    for candidate in candidates:
        key = normalize_candidate_url(candidate.get("url", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        item = dict(candidate)
        item["url"] = key
        result.append(item)
    return result


def summarize_counts(**counts) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items())


def should_stop_keyword_paging(page_candidate_count: int) -> bool:
    return page_candidate_count <= 0


def should_initialize_selenium(use_selenium: bool, crawl_mode: Optional[str]) -> bool:
    if not use_selenium:
        return False
    return str(crawl_mode or "archive_scan").lower() != "topic_search"


def is_challenge_page(html: str) -> bool:
    text = (html or "").lower()
    challenge_markers = [
        "client challenge",
        "/_fs-ch-",
        "checking your browser",
        "everything we learned from powering",
        "powering 20% of the internet",
    ]
    return any(marker in text for marker in challenge_markers)


def detect_supported_family(url: str) -> Optional[str]:
    parsed = urlparse((url or "").strip())
    host = parsed.netloc.lower()
    if host.endswith("nature.com"):
        return "nature"
    if host.endswith("cell.com"):
        return "cell"
    if host.endswith("plos.org"):
        return "plos"
    if host.endswith("science.org") or host.endswith("sciencemag.org"):
        return "science"
    return None


def detect_supported_family_by_name(name: str) -> Optional[str]:
    return None


def detect_journal_family(url: str) -> str:
    return detect_supported_family(url) or "other"


def _find_column(fieldnames: Iterable[str], candidates: Iterable[str], fallback_index: int) -> str:
    fields = list(fieldnames or [])
    for candidate in candidates:
        if candidate in fields:
            return candidate
    if len(fields) > fallback_index:
        return fields[fallback_index]
    raise ValueError("CSV missing required columns")


def _find_optional_column(fieldnames: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    fields = list(fieldnames or [])
    for candidate in candidates:
        if candidate in fields:
            return candidate
    return None


def _normalized_issn_values(row: dict, columns: Iterable[Optional[str]]) -> Tuple[str, ...]:
    values = []
    for column in columns:
        if not column:
            continue
        raw = row.get(column)
        for part in re.split(r"[;,/|\s]+", str(raw or "")):
            compact = part.strip().upper().replace("-", "")
            if re.match(r"^\d{7}[\dX]$", compact):
                formatted = f"{compact[:4]}-{compact[4:]}"
                if formatted not in values:
                    values.append(formatted)
    return tuple(values)


def load_supported_journals_from_csv(csv_path: Union[str, Path]) -> Tuple[Dict[str, List[dict]], List[dict]]:
    groups = {family: [] for family in PLATFORM_FAMILIES}
    skipped = groups["other"]
    seen_journal_keys = set()
    text = None
    last_error = None
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            with open(csv_path, encoding=encoding, newline="") as f:
                text = f.read()
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise last_error

    with io.StringIO(text, newline="") as f:
        reader = csv.DictReader(f)
        name_col = _find_column(reader.fieldnames, ["期刊名称", "journal", "Journal"], 0)
        url_col = _find_column(reader.fieldnames, ["期刊URL", "url", "URL"], 13)
        issn_col = _find_optional_column(reader.fieldnames, ["ISSN", "issn"])
        eissn_col = _find_optional_column(reader.fieldnames, ["EISSN", "eissn", "eISSN"])
        for row in reader:
            name = (row.get(name_col) or "").strip()
            url = normalize_candidate_url(row.get(url_col) or "")
            journal_key = (url, _normalized_issn_values(row, (issn_col, eissn_col)))
            if not url or journal_key in seen_journal_keys:
                continue
            seen_journal_keys.add(journal_key)
            csv_url = url
            family = detect_journal_family(url)
            item = {
                "name": name,
                "link": url,
                "csv_link": csv_url,
                "source_row": row,
                "family": family,
            }
            groups[family].append(item)
    return groups, skipped
