# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class CrawlCheckpointStore:
    """SQLite checkpoint store used to skip already reviewed/crawled papers."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path or Path(__file__).resolve().parent / "crawl_checkpoint.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_articles (
                    scope TEXT NOT NULL,
                    article_key TEXT NOT NULL,
                    journal TEXT,
                    subjournal TEXT,
                    title TEXT,
                    doi TEXT,
                    url TEXT,
                    status TEXT,
                    updated_time TEXT NOT NULL,
                    PRIMARY KEY(scope, article_key)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_processed_keys(self, scope):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT article_key FROM processed_articles WHERE scope = ?",
                (scope,),
            ).fetchall()
        finally:
            conn.close()
        return {normalize_article_key(row[0]) for row in rows if normalize_article_key(row[0])}

    def mark_processed(self, scope, article, journal="", subjournal="", status="processed"):
        key = article_key(article)
        if not key:
            return False
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO processed_articles (
                    scope, article_key, journal, subjournal, title, doi, url, status, updated_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, article_key) DO UPDATE SET
                    journal = excluded.journal,
                    subjournal = excluded.subjournal,
                    title = excluded.title,
                    doi = excluded.doi,
                    url = excluded.url,
                    status = excluded.status,
                    updated_time = excluded.updated_time
                """,
                (
                    scope,
                    key,
                    journal,
                    subjournal,
                    article.get("title") or "",
                    article.get("doi") or "",
                    article.get("link") or article.get("url") or "",
                    status,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return True


def checkpoint_scope(topic_name, journal, subjournal, start_date, end_date):
    parts = [topic_name or "topic", journal or "", subjournal or "", str(start_date), str(end_date)]
    return "|".join(str(part).strip().lower() for part in parts)


def article_key(article):
    article = article or {}
    doi = normalize_doi(article.get("doi"))
    if doi:
        return "doi:" + doi
    url = str(article.get("link") or article.get("url") or "").strip()
    doi = normalize_doi(url)
    if doi:
        return "doi:" + doi
    if url:
        return "url:" + _normalize_url(url)
    title = " ".join(str(article.get("title") or "").lower().split())
    date = str(article.get("date") or "").strip()
    if title:
        return "title:" + title + "|" + date
    return ""


def normalize_article_key(key):
    text = str(key or "").strip()
    if not text:
        return ""
    if text.lower().startswith("doi:"):
        doi = normalize_doi(text[4:])
        return "doi:" + doi if doi else text.lower()
    if text.lower().startswith("url:"):
        doi = normalize_doi(text[4:])
        if doi:
            return "doi:" + doi
        return "url:" + _normalize_url(text[4:])
    return text.lower()


def _normalize_url(url):
    return url.split("#", 1)[0].strip().rstrip("/").lower()


def normalize_doi(value):
    text = str(value or "").strip()
    if not text:
        return ""
    lower = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "doi/"):
        if lower.startswith(prefix):
            text = text[len(prefix):]
            lower = text.lower()
            break
    if "doi.org/" in lower:
        text = text[lower.rfind("doi.org/") + len("doi.org/"):]
    import re
    match = re.search(r"10\.\d{4,9}/[^\s]+", text, re.I)
    if not match:
        return ""
    return match.group(0).strip().rstrip(".,;)")
