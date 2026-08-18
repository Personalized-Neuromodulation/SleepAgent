# -*- coding: utf-8 -*-
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path


class JournalArticleCache:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path or Path.cwd() / "journal_cache.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    doi TEXT PRIMARY KEY,
                    title TEXT,
                    abstract TEXT,
                    date TEXT,
                    url TEXT,
                    authors TEXT,
                    journal TEXT,
                    article_type TEXT,
                    extra_json TEXT,
                    updated_time TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, doi):
        doi = (doi or "").strip()
        if not doi:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT doi, title, abstract, date, url, authors, journal, article_type, extra_json
                FROM articles WHERE doi = ?
                """,
                (doi,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return {
            "doi": row[0],
            "title": row[1] or "",
            "abstract": row[2] or "",
            "date": self._parse_date(row[3]),
            "url": row[4] or "",
            "authors": row[5] or "",
            "journal": row[6] or "",
            "article_type": row[7] or "",
            **json.loads(row[8] or "{}"),
        }

    def upsert(self, article):
        doi = (article or {}).get("doi") or ""
        doi = doi.strip()
        if not doi:
            return False
        article_date = self._date_text(article.get("date"))
        known = {"doi", "title", "abstract", "date", "url", "authors", "journal", "article_type"}
        extra = {k: v for k, v in article.items() if k not in known}
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO articles (
                    doi, title, abstract, date, url, authors, journal, article_type, extra_json, updated_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doi) DO UPDATE SET
                    title = excluded.title,
                    abstract = excluded.abstract,
                    date = excluded.date,
                    url = excluded.url,
                    authors = excluded.authors,
                    journal = excluded.journal,
                    article_type = excluded.article_type,
                    extra_json = excluded.extra_json,
                    updated_time = excluded.updated_time
                """,
                (
                    doi,
                    article.get("title") or "",
                    article.get("abstract") or "",
                    article_date or "",
                    article.get("url") or "",
                    article.get("authors") or "",
                    article.get("journal") or "",
                    article.get("article_type") or article.get("type") or "",
                    json.dumps(extra, ensure_ascii=False, default=str),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return True

    def _date_text(self, value):
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat()
        return str(value) if value else ""

    def _parse_date(self, value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return value
