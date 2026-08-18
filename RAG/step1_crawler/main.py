#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一学术期刊爬虫系统 - 主题爬取模式（仅从 CSV 加载期刊）
- 强制使用主题关键词预筛
- 单次 LLM 复核（不再双重仲裁）
- 仅导出相关（related）和复核失败（review_failed）文章
"""

import argparse
import csv
import gc
import importlib.util
import logging
import sys
import os
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List
import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor


BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import openpyxl


# 导入内部模块

from tools.topic_utils import PLATFORM_FAMILIES, TopicConfig, article_matches_topic, load_supported_journals_from_csv, safe_path_name
from crawl_checkpoint import CrawlCheckpointStore, article_key, checkpoint_scope

# EXPORTS_DIR = BASE_DIR / "exports"
EXPORTS_DIR = Path("/data/RAG/step1_crawler/exports/")

os.makedirs(EXPORTS_DIR / "logs", exist_ok=True)

# 日志配置
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(EXPORTS_DIR / "logs" / "crawler.log", encoding="utf-8-sig"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


ALL_INFO_FIELDS = [
    "title",
    "abstract",
    "date",
    "doi",
    "link",
    "authors",
    "journal",
    "article_type",
    "source",
    "quality_score",
    "type",
    "issue",
    "expanded_title_matched",
    "abstract_repaired",
    "abstract_repair_status",
    "abstract_repair_method",
    "abstract_source",
    "publisher_attempted",
    "publisher_status",
    "publisher_http_status",
    "publisher_url",
    "doi_abstract_attempted",
]

RESULT_EXTRA_FIELDS = [
    "review_input",
    "topic_keyword_matched",
    "review_status",
    "is_related",
    "reason",
]



def build_export_path(export_format, filename, folder_name=None, topic_name=None, platform_name=None):
    """构建导出文件路径（按主题/子刊组织）"""
    if topic_name and platform_name and folder_name:
        return str(
            EXPORTS_DIR
            / safe_path_name(topic_name)
            / safe_path_name(platform_name.lower())
            / safe_path_name(folder_name)
            / filename
        )
    if topic_name and folder_name:
        return str(EXPORTS_DIR / safe_path_name(topic_name) / safe_path_name(folder_name) / filename)
    # 以下为兜底，但主题模式总会传入 folder_name 和 topic_name
    subdir = 'excel' if export_format == 'xlsx' else 'csv' if export_format == 'csv' else 'json'
    return str(EXPORTS_DIR / subdir / filename)


class ConfigManager:
    """配置管理（仅加载 config.yaml，不再处理期刊列表）"""
    def __init__(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            text = f.read()
        try:
            import yaml
            self.config = yaml.safe_load(text)
        except ImportError:
            self.config = self._load_simple_yaml(text)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def _load_simple_yaml(self, text):
        config = {}
        current_key = None
        for raw_line in text.splitlines():
            line = raw_line.split('#', 1)[0].rstrip()
            if not line.strip():
                continue
            if line.lstrip().startswith('-') and current_key:
                value = line.lstrip()[1:].strip().strip('"').strip("'")
                config.setdefault(current_key, []).append(value)
                continue
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            if value == '':
                config[key] = []
            elif value.lower() in ('true', 'false'):
                config[key] = value.lower() == 'true'
            else:
                config[key] = value.strip('"').strip("'")
        return config


@dataclass(frozen=True)
class RunConfig:
    journal_csv: str
    start_date: str
    end_date: str
    export_format: str
    journals: str = None
    subjournal: str = None


def resolve_run_config(args, config):
    return RunConfig(
        journal_csv=args.journal_csv or config.get('RUN_JOURNAL_CSV') or 'D:/crawler2025/2025_Q1_IF_5.csv',
        start_date=args.start_date or config.get('RUN_START_DATE'),
        end_date=args.end_date or config.get('RUN_END_DATE'),
        export_format=args.format or config.get('RUN_FORMAT', 'xlsx'),
        journals=getattr(args, 'journals', None) or config.get('RUN_JOURNALS'),
        subjournal=args.subjournal or config.get('RUN_SUBJOURNAL'),
    )


class CrawlerSystem:
    """主题爬虫系统"""
    def __init__(self):
        self.config_manager = ConfigManager()
        self.parsers = {}
        self.agents = {}
        self.saved_files = []
        self.checkpoint_store = None
        self.checkpoint_stores = {}
        self._expanded_title_terms = None

    def get_checkpoint_store(self, journal_type):
        if self.checkpoint_store is not None:
            return self.checkpoint_store
        key = safe_path_name(str(journal_type or "other").strip().lower() or "other")
        if key not in self.checkpoint_stores:
            self.checkpoint_stores[key] = CrawlCheckpointStore(
                EXPORTS_DIR / f"{key}_crawl_checkpoint.db"
            )
        return self.checkpoint_stores[key]

    def initialize_journal(self, journal_name):
        """初始化期刊的 Agent 和 Parser"""
        from agent import PaperAgent
        from parser.factory import create_parser
        # parser_spec = importlib.util.spec_from_file_location("crawler_light_parser", BASE_DIR / "parser.py")
        # parser_module = importlib.util.module_from_spec(parser_spec)
        # parser_spec.loader.exec_module(parser_module)
        # create_parser = parser_module.create_parser

        current_logger = logging.getLogger(__name__)
        self.agents[journal_name] = PaperAgent(logger=current_logger)
        # self.parsers[journal_name] = create_parser(journal_name, self.agents[journal_name])
        self.parsers[journal_name] = create_parser(
        journal_name,
        self.agents[journal_name]
        )
        logger.info(f"{journal_name.upper()} 组件初始化完成")

    def append_articles_to_file(self, articles, journal_type, category, start_date_str, end_date_str,
                                export_format='xlsx', folder_name=None, topic_name=None, platform_name=None):
        """追加文章到文件（支持按子刊+主题目录保存）"""
        if not articles:
            return
        try:
            # 文件名：主题_类别_日期范围.扩展名
            filename = f"{safe_path_name(topic_name)}_{category}_{start_date_str}_{end_date_str}.{export_format}"
            filepath = build_export_path(
                export_format,
                filename,
                folder_name=folder_name,
                topic_name=topic_name,
                platform_name=platform_name,
            )
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            if pd is None:
                raise RuntimeError("pandas is required to export crawler results")
            new_df = pd.DataFrame(articles)
            if os.path.exists(filepath):
                if export_format == 'xlsx':
                    existing = pd.read_excel(filepath)
                    combined = pd.concat([existing, new_df], ignore_index=True)
                    combined = self._dedupe_export_rows(combined)
                    combined.to_excel(filepath, index=False, engine='openpyxl')
                elif export_format == 'csv':
                    existing = pd.read_csv(filepath, encoding='utf-8-sig')
                    combined = pd.concat([existing, new_df], ignore_index=True)
                    combined = self._dedupe_export_rows(combined)
                    combined.to_csv(filepath, index=False, encoding='utf-8-sig')
                elif export_format == 'json':
                    with open(filepath, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    existing.extend(articles)
                    existing = self._dedupe_article_list(existing)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(existing, f, ensure_ascii=False, indent=2, default=str)
            else:
                if export_format == 'xlsx':
                    new_df.to_excel(filepath, index=False, engine='openpyxl')
                elif export_format == 'csv':
                    new_df.to_csv(filepath, index=False, encoding='utf-8-sig')
                elif export_format == 'json':
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(articles, f, ensure_ascii=False, indent=2, default=str)

            logger.info(f"追加 {len(articles)} 篇{category}文章到: {filepath}")
            if filepath not in self.saved_files:
                self.saved_files.append(filepath)
        except Exception as e:
            logger.error(f"追加文章失败: {e}")

    def append_articles_to_named_csv(self, articles, filename, folder_name=None, topic_name=None, platform_name=None, overwrite=False):
        if not articles:
            return None
        filepath = build_export_path(
            "csv",
            filename,
            folder_name=folder_name,
            topic_name=topic_name,
            platform_name=platform_name,
        )
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        if pd is None:
            raise RuntimeError("pandas is required to export crawler results")
        new_df = pd.DataFrame(articles)
        if os.path.exists(filepath) and not overwrite:
            existing = pd.read_csv(filepath, encoding="utf-8-sig")
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined = self._dedupe_export_rows(combined)
        else:
            combined = self._dedupe_export_rows(new_df)
        combined.to_csv(filepath, index=False, encoding="utf-8-sig")
        logger.info(f"追加 {len(articles)} 篇metadata到 {filepath}")
        if filepath not in self.saved_files:
            self.saved_files.append(filepath)
        return filepath

    def _dedupe_export_rows(self, df):
        if df is None or df.empty:
            return df
        rows = []
        index_by_key = {}
        for _, row in df.iterrows():
            item = row.to_dict()
            key = article_key(item)
            if key and key in index_by_key:
                existing = rows[index_by_key[key]]
                for field, value in item.items():
                    if value is not None and str(value).strip() and str(value).lower() != "nan":
                        existing[field] = value
                continue
            if key:
                index_by_key[key] = len(rows)
            rows.append(item)
        return pd.DataFrame(rows)

    def _dedupe_article_list(self, articles):
        result = []
        seen = set()
        for article in articles or []:
            key = article_key(article)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            result.append(article)
        return result

    def _export_filepath(self, category, start_date_str, end_date_str, export_format,
                         folder_name=None, topic_name=None, platform_name=None):
        filename = f"{safe_path_name(topic_name)}_{category}_{start_date_str}_{end_date_str}.{export_format}"
        return build_export_path(
            export_format,
            filename,
            folder_name=folder_name,
            topic_name=topic_name,
            platform_name=platform_name,
        )

    def _load_existing_export_keys(self, start_date_str, end_date_str, export_format,
                                   folder_name=None, topic_name=None, platform_name=None):
        keys = set()
        for category in ("related", "review_failed"):
            filepath = self._export_filepath(
                category,
                start_date_str,
                end_date_str,
                export_format,
                folder_name=folder_name,
                topic_name=topic_name,
                platform_name=platform_name,
            )
            if not os.path.exists(filepath):
                continue
            try:
                if export_format == "xlsx":
                    rows = pd.read_excel(filepath).to_dict("records")
                elif export_format == "csv":
                    rows = pd.read_csv(filepath, encoding="utf-8-sig").to_dict("records")
                elif export_format == "json":
                    with open(filepath, "r", encoding="utf-8") as f:
                        rows = json.load(f)
                else:
                    rows = []
                for row in rows or []:
                    key = article_key(row)
                    if key:
                        keys.add(key)
            except Exception as e:
                logger.warning(f"读取断点导出文件失败，跳过该文件: {filepath} - {e}")
        return keys

    def _all_info_path(
        self,
        journal,
        subjournal_name,
        topic_name,
    ):
        return build_export_path(
            "csv",
            "all_info.csv",
            folder_name=subjournal_name,
            topic_name=topic_name,
            platform_name=journal,
        )

    def _load_article_keys_from_csv(self, path):
        """Stream article_key values from an existing CSV without loading rows into memory."""
        keys = set()
        if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
            return keys

        try:
            with open(
                path,
                "r",
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            ) as handle:
                for row in csv.DictReader(handle):
                    key = article_key(row)
                    if key:
                        keys.add(key)
        except Exception as exc:
            logger.warning(
                "读取已有CSV article_key失败，按空集合继续: %s - %s",
                path,
                exc,
            )

        return keys

    def _related_csv_path(
        self,
        topic_name,
        subjournal_name,
        journal,
        start_date_str,
        end_date_str,
    ):
        return build_export_path(
            "csv",
            (
                f"{safe_path_name(topic_name)}_related_"
                f"{start_date_str}_{end_date_str}.csv"
            ),
            folder_name=subjournal_name,
            topic_name=topic_name,
            platform_name=journal,
        )

    def _prepare_all_info_csv(
        self,
        journal,
        subjournal_name,
        topic_name,
    ):
        """Return the persistent all_info.csv path WITHOUT deleting old metadata."""
        path = self._all_info_path(
            journal,
            subjournal_name,
            topic_name,
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if path not in self.saved_files:
            self.saved_files.append(path)

        return path

    def _append_new_metadata_batch_to_all_info(
        self,
        batch,
        all_info_path,
        subjournal_name,
        existing_article_keys,
        issue_title=None,
    ):
        """Append only metadata rows whose article_key is not already in all_info.csv.

        The in-memory set contains only compact article keys; the full historical
        corpus remains on disk.
        """
        if not batch:
            return 0, 0

        write_header = (
            not os.path.exists(all_info_path)
            or os.path.getsize(all_info_path) == 0
        )

        appended = 0
        skipped_existing = 0

        with open(
            all_info_path,
            "a",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=ALL_INFO_FIELDS,
                extrasaction="ignore",
            )

            if write_header:
                writer.writeheader()

            for paper in batch:
                row = self._normalize_metadata_for_disk(
                    paper,
                    subjournal_name,
                    issue_title=issue_title,
                )
                key = article_key(row)

                if key and key in existing_article_keys:
                    skipped_existing += 1
                    continue

                writer.writerow(row)
                appended += 1

                if key:
                    existing_article_keys.add(key)

        return appended, skipped_existing

    def _reset_all_info_csv(
        self,
        journal,
        subjournal_name,
        topic_name,
    ):
        """Start a fresh on-disk metadata state for the current journal run."""
        path = self._all_info_path(
            journal,
            subjournal_name,
            topic_name,
        )

        os.makedirs(
            os.path.dirname(path),
            exist_ok=True,
        )

        if os.path.exists(path):
            os.remove(path)

        if path not in self.saved_files:
            self.saved_files.append(path)

        return path

    @staticmethod
    def _csv_bool(value):
        if isinstance(value, bool):
            return value

        return str(value or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

    @staticmethod
    def _stringify_csv_value(value):
        if value is None:
            return ""

        return str(value)

    def _normalize_metadata_for_disk(
        self,
        paper,
        subjournal_name,
        issue_title=None,
    ):
        item = {
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", ""),
            "date": paper.get("date"),
            "doi": paper.get("doi", ""),
            "link": (
                paper.get("url", "")
                or paper.get("link", "")
            ),
            "authors": paper.get("authors", ""),
            "journal": paper.get(
                "journal",
                subjournal_name,
            ),
            "article_type": paper.get(
                "article_type",
                paper.get("type", ""),
            ),
            "source": paper.get("source", ""),
            "quality_score": paper.get(
                "quality_score",
                "",
            ),
            "type": "full",
            "issue": issue_title or paper.get(
                "issue",
                "",
            ),
            "expanded_title_matched": "",
            "abstract_repaired": "",
            "abstract_repair_status": "",
            "abstract_repair_method": "",
            "abstract_source": "",
            "publisher_attempted": "",
            "publisher_status": "",
            "publisher_http_status": "",
            "publisher_url": "",
            "doi_abstract_attempted": "",
        }

        return {
            field: self._stringify_csv_value(
                item.get(field, "")
            )
            for field in ALL_INFO_FIELDS
        }

    def _append_metadata_batch_to_all_info(
        self,
        batch,
        all_info_path,
        subjournal_name,
        issue_title=None,
    ):
        """Append one bounded metadata batch without reading existing CSV."""
        if not batch:
            return 0

        write_header = (
            not os.path.exists(all_info_path)
            or os.path.getsize(all_info_path) == 0
        )

        written = 0

        with open(
            all_info_path,
            "a",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=ALL_INFO_FIELDS,
                extrasaction="ignore",
            )

            if write_header:
                writer.writeheader()

            for paper in batch:
                writer.writerow(
                    self._normalize_metadata_for_disk(
                        paper,
                        subjournal_name,
                        issue_title=issue_title,
                    )
                )
                written += 1

        logger.info(
            "追加 %s 篇metadata到 %s",
            written,
            all_info_path,
        )

        return written


    def _abstract_repair_parallel_config(self):
        """Load bounded abstract-repair concurrency settings from config.yaml."""
        def _read_int(key, default, minimum=1, maximum=None):
            try:
                value = int(self.config_manager.get(key, default))
            except Exception:
                value = int(default)
            value = max(minimum, value)
            if maximum is not None:
                value = min(maximum, value)
            return value

        workers = _read_int(
            "ABSTRACT_REPAIR_MAX_WORKERS",
            4,
            minimum=1,
            maximum=16,
        )
        repair_batch_size = _read_int(
            "ABSTRACT_REPAIR_BATCH_SIZE",
            32,
            minimum=1,
            maximum=512,
        )
        scan_batch_size = _read_int(
            "ABSTRACT_REPAIR_SCAN_BATCH_SIZE",
            256,
            minimum=repair_batch_size,
            maximum=4096,
        )
        return workers, repair_batch_size, scan_batch_size

    def _parallel_repair_rows(
        self,
        rows,
        journal,
        subjournal_name,
        mode,
        executor,
    ):
        """Run network-bound abstract repair concurrently and preserve row order.

        Worker threads NEVER write CSV and NEVER mutate the caller's row object.
        """
        rows = list(rows or [])
        if not rows:
            return []

        parser = self.parsers.get(journal)
        if parser is None:
            return [dict(row) for row in rows]

        def _worker(source_row):
            original = dict(source_row)
            try:
                if mode == "publisher_then_doi":
                    method = getattr(
                        parser,
                        "repair_abstract_publisher_then_doi",
                        None,
                    )
                elif mode == "doi_only":
                    method = getattr(
                        parser,
                        "repair_abstract_by_doi",
                        None,
                    )
                else:
                    method = None

                if not callable(method):
                    result = dict(original)
                    result["abstract_repair_status"] = "missing_repair_method"
                    result["abstract_repair_method"] = "none"
                    return result

                repaired = method(
                    dict(original),
                    subjournal_name,
                )
                return repaired or dict(original)

            except Exception as exc:
                result = dict(original)
                result["abstract_repair_status"] = "error"
                result["abstract_repair_method"] = "none"
                result["_repair_error"] = str(exc)
                return result

        # map() executes concurrently but yields results in source-row order.
        return list(executor.map(_worker, rows))

    def _merge_repair_result_into_row(self, row, repaired):
        """Merge one detached worker result into the main-thread CSV row."""
        repaired = repaired or {}

        for field in (
            "publisher_attempted",
            "publisher_status",
            "publisher_http_status",
            "publisher_url",
            "doi_abstract_attempted",
            "abstract_repair_status",
            "abstract_repair_method",
            "abstract_source",
        ):
            value = repaired.get(field)
            if isinstance(value, bool):
                row[field] = "true" if value else "false"
            elif value is not None:
                row[field] = str(value)

        repaired_abstract = str(
            repaired.get("abstract") or ""
        ).strip()

        if repaired_abstract:
            row["abstract"] = repaired_abstract
            row["abstract_repaired"] = "true"
            row["abstract_repair_status"] = "repaired"
        else:
            row["abstract"] = ""
            row["abstract_repaired"] = "false"
            row["abstract_repair_status"] = (
                row.get("abstract_repair_status") or "not_found"
            )
            row["abstract_repair_method"] = (
                row.get("abstract_repair_method") or "none"
            )

        # Never overwrite metadata already collected by the platform parser.
        for field in (
            "title",
            "date",
            "doi",
            "link",
            "authors",
            "journal",
            "article_type",
        ):
            if str(row.get(field) or "").strip():
                continue
            value = repaired.get(field)
            if value is not None and str(value).strip():
                row[field] = str(value)

        return row

    def _repair_all_info_csv(
        self,
        all_info_path,
        journal,
        subjournal_name,
    ):
        """Parallel low-memory publisher -> DOI abstract repair.

        Pipeline:
            all_info.csv
            -> bounded scan block
            -> title-expanded candidate selection
            -> ThreadPoolExecutor network repair
            -> main-thread merge/write in original order
            -> all_info.csv.repairing.tmp
            -> atomic os.replace()

        CSV writing and statistics remain single-threaded.
        """
        parser = self.parsers.get(journal)

        if not parser or not hasattr(
            parser,
            "repair_abstract_publisher_then_doi",
        ):
            logger.warning(
                f"{journal} {subjournal_name}: "
                f"parser缺少repair_abstract_publisher_then_doi"
            )

        workers, repair_batch_size, scan_batch_size = (
            self._abstract_repair_parallel_config()
        )

        # Parallel repair is enabled only when BaseParser declares that it uses
        # per-thread HTTP clients. This prevents sharing requests.Session across
        # worker threads by mistake.
        if (
            workers > 1
            and parser is not None
            and not getattr(
                parser,
                "thread_safe_abstract_repair",
                False,
            )
        ):
            logger.warning(
                f"{journal} {subjournal_name}: parser未声明"
                f"thread_safe_abstract_repair，自动降级为单线程；"
                f"请同步替换并行版 parser/base.py"
            )
            workers = 1

        expanded_terms = self._load_expanded_title_terms()
        temp_path = f"{all_info_path}.repairing.tmp"

        total = 0
        abstract_present = 0
        abstract_missing = 0
        expanded_title_matched = 0
        repair_attempted = 0
        repair_count = 0
        repair_failed = 0

        publisher_attempted = 0
        publisher_repaired = 0
        publisher_antibot = 0
        publisher_no_abstract = 0
        publisher_failed_other = 0

        doi_attempted = 0
        doi_repaired = 0

        source_counts = {}
        publisher_status_counts = {}

        logger.info(
            f"{journal} {subjournal_name}: 并行摘要补全启动 "
            f"workers={workers}, "
            f"repair_batch_size={repair_batch_size}, "
            f"scan_batch_size={scan_batch_size}"
        )

        def _account_result(row, repaired):
            nonlocal repair_count
            nonlocal repair_failed
            nonlocal publisher_attempted
            nonlocal publisher_repaired
            nonlocal publisher_antibot
            nonlocal publisher_no_abstract
            nonlocal publisher_failed_other
            nonlocal doi_attempted
            nonlocal doi_repaired

            self._merge_repair_result_into_row(
                row,
                repaired,
            )

            pub_attempted = self._csv_bool(
                row.get("publisher_attempted")
            )
            if pub_attempted:
                publisher_attempted += 1

            pub_status = str(
                row.get("publisher_status") or ""
            ).strip()

            if pub_status:
                publisher_status_counts[pub_status] = (
                    publisher_status_counts.get(pub_status, 0) + 1
                )

            if pub_status == "anti_bot":
                publisher_antibot += 1
            elif pub_status == "no_abstract":
                publisher_no_abstract += 1
            elif (
                pub_attempted
                and pub_status
                not in (
                    "success",
                    "anti_bot",
                    "no_abstract",
                )
            ):
                publisher_failed_other += 1

            doi_used = self._csv_bool(
                row.get("doi_abstract_attempted")
            )
            if doi_used:
                doi_attempted += 1

            if not str(row.get("abstract") or "").strip():
                repair_failed += 1
                return

            method = str(
                row.get("abstract_repair_method") or ""
            ).strip()

            if method == "publisher":
                publisher_repaired += 1
            elif method == "doi_api":
                doi_repaired += 1

            abstract_source = str(
                row.get("abstract_source") or ""
            ).strip()

            if abstract_source:
                source_counts[abstract_source] = (
                    source_counts.get(abstract_source, 0) + 1
                )

            repair_count += 1

        def _process_scan_block(block, writer, executor):
            nonlocal total
            nonlocal abstract_present
            nonlocal abstract_missing
            nonlocal expanded_title_matched
            nonlocal repair_attempted

            prepared_rows = []
            candidates = []
            candidate_positions = []

            for original_row in block:
                row = dict(original_row)
                total += 1

                abstract = str(
                    row.get("abstract") or ""
                ).strip()

                if abstract:
                    abstract_present += 1
                    row["abstract_repaired"] = (
                        row.get("abstract_repaired") or "false"
                    )
                    row["abstract_repair_status"] = (
                        row.get("abstract_repair_status") or "existing"
                    )
                    row["abstract_repair_method"] = (
                        row.get("abstract_repair_method") or "existing"
                    )
                    row["expanded_title_matched"] = (
                        row.get("expanded_title_matched") or "false"
                    )
                    row["publisher_attempted"] = (
                        row.get("publisher_attempted") or "false"
                    )
                    row["doi_abstract_attempted"] = (
                        row.get("doi_abstract_attempted") or "false"
                    )
                    prepared_rows.append(row)
                    continue

                abstract_missing += 1

                title = str(
                    row.get("title") or ""
                )

                title_matched = bool(
                    expanded_terms
                    and self._text_matches_any_term(
                        title,
                        expanded_terms,
                    )
                )

                row["expanded_title_matched"] = (
                    "true" if title_matched else "false"
                )

                if not title_matched:
                    row["abstract_repaired"] = "false"
                    row["abstract_repair_status"] = "not_candidate"
                    row["abstract_repair_method"] = "none"
                    row["publisher_attempted"] = "false"
                    row["publisher_status"] = "not_candidate"
                    row["doi_abstract_attempted"] = "false"
                    prepared_rows.append(row)
                    continue

                expanded_title_matched += 1
                repair_attempted += 1

                candidate_positions.append(
                    len(prepared_rows)
                )
                candidates.append(
                    dict(row)
                )
                prepared_rows.append(row)

            repaired_candidates = []

            # Bound the submitted candidate list even if one scan block has
            # many repairable rows.
            for offset in range(
                0,
                len(candidates),
                repair_batch_size,
            ):
                batch = candidates[
                    offset:offset + repair_batch_size
                ]
                if not batch:
                    continue

                logger.info(
                    f"{journal} {subjournal_name}: "
                    f"并发补摘要 batch="
                    f"{offset // repair_batch_size + 1}, "
                    f"size={len(batch)}, workers={workers}"
                )

                repaired_candidates.extend(
                    self._parallel_repair_rows(
                        batch,
                        journal,
                        subjournal_name,
                        mode="publisher_then_doi",
                        executor=executor,
                    )
                )

            for position, repaired in zip(
                candidate_positions,
                repaired_candidates,
            ):
                row = prepared_rows[position]

                repair_error = str(
                    repaired.get("_repair_error") or ""
                ).strip()
                if repair_error:
                    logger.warning(
                        f"{journal} {subjournal_name}: "
                        f"摘要补全异常 doi={row.get('doi', '')}: "
                        f"{repair_error}"
                    )

                _account_result(
                    row,
                    repaired,
                )

            # CSV is written only by the main thread, preserving source order.
            writer.writerows(prepared_rows)

        try:
            with open(
                all_info_path,
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as source_handle, open(
                temp_path,
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as target_handle, ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="abstract-repair",
            ) as executor:
                reader = csv.DictReader(
                    source_handle
                )

                fieldnames = list(
                    reader.fieldnames
                    or ALL_INFO_FIELDS
                )

                for field in ALL_INFO_FIELDS:
                    if field not in fieldnames:
                        fieldnames.append(field)

                writer = csv.DictWriter(
                    target_handle,
                    fieldnames=fieldnames,
                    extrasaction="ignore",
                )
                writer.writeheader()

                scan_block = []

                for row in reader:
                    scan_block.append(row)

                    if len(scan_block) >= scan_batch_size:
                        _process_scan_block(
                            scan_block,
                            writer,
                            executor,
                        )
                        scan_block.clear()

                if scan_block:
                    _process_scan_block(
                        scan_block,
                        writer,
                        executor,
                    )
                    scan_block.clear()

            # Atomic replacement remains unchanged.
            os.replace(
                temp_path,
                all_info_path,
            )

        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

        logger.info(
            f"{journal} {subjournal_name}: "
            f"all_info.csv摘要更新完成 "
            f"workers={workers}, "
            f"total={total}, "
            f"abstract_present={abstract_present}, "
            f"abstract_missing={abstract_missing}, "
            f"expanded_title_matched={expanded_title_matched}, "
            f"repair_attempted={repair_attempted}, "
            f"publisher_attempted={publisher_attempted}, "
            f"publisher_repaired={publisher_repaired}, "
            f"publisher_antibot={publisher_antibot}, "
            f"publisher_no_abstract={publisher_no_abstract}, "
            f"publisher_failed_other={publisher_failed_other}, "
            f"doi_attempted={doi_attempted}, "
            f"doi_repaired={doi_repaired}, "
            f"repaired_total={repair_count}, "
            f"repair_failed={repair_failed}, "
            f"sources={source_counts}, "
            f"publisher_statuses={publisher_status_counts}"
        )

        return {
            "candidate": total,
            "abstract_present": abstract_present,
            "abstract_missing": abstract_missing,
            "expanded_title_matched": expanded_title_matched,
            "abstract_repair_attempted": repair_attempted,
            "publisher_attempted": publisher_attempted,
            "publisher_repaired": publisher_repaired,
            "publisher_antibot": publisher_antibot,
            "publisher_no_abstract": publisher_no_abstract,
            "publisher_failed_other": publisher_failed_other,
            "publisher_statuses": publisher_status_counts,
            "doi_abstract_attempted": doi_attempted,
            "doi_abstract_repaired": doi_repaired,
            "abstract_repaired": repair_count,
            "abstract_repair_failed": repair_failed,
            "abstract_sources": source_counts,
        }


    def _reset_csv_output(self, path):
        if os.path.exists(path):
            os.remove(path)

        os.makedirs(
            os.path.dirname(path),
            exist_ok=True,
        )

    def _append_result_rows_csv(
        self,
        path,
        rows,
    ):
        """Append LLM results without reading the existing result file."""
        if not rows:
            return 0

        fieldnames = (
            list(ALL_INFO_FIELDS)
            + list(RESULT_EXTRA_FIELDS)
        )

        write_header = (
            not os.path.exists(path)
            or os.path.getsize(path) == 0
        )

        count = 0

        with open(
            path,
            "a",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )

            if write_header:
                writer.writeheader()

            for row in rows:
                writer.writerow({
                    field: self._stringify_csv_value(
                        row.get(field, "")
                    )
                    for field in fieldnames
                })
                count += 1

        if path not in self.saved_files:
            self.saved_files.append(path)

        return count

    def _review_updated_all_info_csv(
        self,
        all_info_path,
        journal,
        subjournal_name,
        agent,
        start_date_str,
        end_date_str,
    ):
        """Reopen updated all_info.csv and run TOPIC_KEYWORDS -> batched LLM.

        Pipeline:
            1) Scan the updated all_info.csv exactly once.
            2) Apply TOPIC_KEYWORDS to ALL rows:
               - title + abstract when abstract exists
               - title only when abstract is empty / repair failed
            3) Write only TOPIC-matched rows to a temporary candidate CSV.
            4) After the complete keyword pass, print the exact candidate count.
            5) Read the candidate CSV in bounded chunks and send those rows to LLM.

        This avoids:
            - scanning the full all_info.csv twice;
            - sending LLM work before the keyword prefilter has completed;
            - retaining a potentially large candidate list in memory.
        """
        topic_name = getattr(
            agent,
            "topic_name",
            "topic",
        )

        topic = TopicConfig(
            name=topic_name,
            keywords=list(
                getattr(
                    agent,
                    "topic_keywords",
                    [],
                )
                or []
            ),
        )

        if not topic.keywords:
            logger.warning(
                f"{journal} {subjournal_name}: "
                f"未配置TOPIC_KEYWORDS，仅保留更新后的all_info.csv"
            )
            return {
                "reviewed": 0,
                "saved": 0,
                "related": 0,
                "review_failed": 0,
                "prefiltered": 0,
                "title_only_topic_checked": 0,
                "title_only_reviewed": 0,
            }

        try:
            chunk_size = max(
                1,
                int(
                    self.config_manager.get(
                        "CSV_PROCESS_BATCH_SIZE",
                        100,
                    )
                ),
            )
        except Exception:
            chunk_size = 100

        related_path = self._related_csv_path(
            topic_name,
            subjournal_name,
            journal,
            start_date_str,
            end_date_str,
        )

        failed_path = build_export_path(
            "csv",
            (
                f"{safe_path_name(topic_name)}_review_failed_"
                f"{start_date_str}_{end_date_str}.csv"
            ),
            folder_name=subjournal_name,
            topic_name=topic_name,
            platform_name=journal,
        )

        # Related is a persistent, cumulative high-recall result set.
        # Never reset it on rerun: already accepted Related/Borderline papers
        # are the only TOPIC-matched papers allowed to skip LLM review.
        existing_related_keys = self._load_article_keys_from_csv(
            related_path
        )
        existing_related_before = len(existing_related_keys)

        # review_failed is only a diagnostic output for the current run.
        self._reset_csv_output(failed_path)

        candidate_path = f"{all_info_path}.topic_candidates.tmp.csv"

        total_rows = 0
        topic_matched = 0
        title_abstract_topic_checked = 0
        title_only_topic_checked = 0
        title_abstract_topic_matched = 0
        title_only_topic_matched = 0
        reviewed = 0
        related = 0
        review_failed = 0
        already_related_skipped = 0
        llm_candidate_count = 0

        # --------------------------------------------------------------
        # Phase 1: complete TOPIC_KEYWORDS prefilter over ALL papers.
        # --------------------------------------------------------------
        logger.info(
            f"{journal} {subjournal_name}: "
            f"开始对更新后的all_info.csv全部论文执行TOPIC_KEYWORDS初筛；"
            f"有摘要使用title+abstract，无摘要/修复失败使用title-only"
        )

        try:
            with open(
                all_info_path,
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as source_handle, open(
                candidate_path,
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as candidate_handle:
                reader = csv.DictReader(source_handle)

                candidate_fields = (
                    list(ALL_INFO_FIELDS)
                    + [
                        field
                        for field in RESULT_EXTRA_FIELDS
                        if field not in ALL_INFO_FIELDS
                    ]
                )

                writer = csv.DictWriter(
                    candidate_handle,
                    fieldnames=candidate_fields,
                    extrasaction="ignore",
                )
                writer.writeheader()

                for row in reader:
                    total_rows += 1

                    abstract = str(
                        row.get("abstract")
                        or ""
                    ).strip()

                    if abstract:
                        title_abstract_topic_checked += 1
                        review_input = "title_abstract"
                    else:
                        title_only_topic_checked += 1
                        review_input = "title_only"

                    topic_hit = article_matches_topic(
                        row,
                        topic,
                    )

                    if not topic_hit:
                        continue

                    topic_matched += 1

                    if abstract:
                        title_abstract_topic_matched += 1
                    else:
                        title_only_topic_matched += 1

                    row["review_input"] = review_input
                    row["topic_keyword_matched"] = "true"

                    # High-recall rerun policy:
                    # every TOPIC hit is reviewed again unless it is already
                    # present in the persistent related CSV.
                    key = article_key(row)
                    if key and key in existing_related_keys:
                        already_related_skipped += 1
                        continue

                    llm_candidate_count += 1

                    writer.writerow({
                        field: self._stringify_csv_value(
                            row.get(field, "")
                        )
                        for field in candidate_fields
                    })

            filtered_out = total_rows - topic_matched
            match_rate = (
                (topic_matched / total_rows) * 100.0
                if total_rows
                else 0.0
            )

            logger.info(
                f"{journal} {subjournal_name}: "
                f"TOPIC_KEYWORDS初筛完成 "
                f"input={total_rows}, "
                f"matched={topic_matched}, "
                f"filtered_out={filtered_out}, "
                f"match_rate={match_rate:.2f}%, "
                f"matched_title_abstract={title_abstract_topic_matched}, "
                f"matched_title_only={title_only_topic_matched}, "
                f"already_related_skipped={already_related_skipped}, "
                f"llm_candidates={llm_candidate_count}"
            )

            if topic_matched == 0:
                logger.info(
                    f"{journal} {subjournal_name}: "
                    f"TOPIC_KEYWORDS筛选后剩余0篇，跳过LLM复核"
                )
                if os.path.exists(candidate_path):
                    os.remove(candidate_path)

                return {
                    "reviewed": 0,
                    "saved": 0,
                    "related": 0,
                    "review_failed": 0,
                    "prefiltered": 0,
                    "title_abstract_topic_checked": title_abstract_topic_checked,
                    "title_only_topic_checked": title_only_topic_checked,
                    "title_only_reviewed": 0,
                    "title_abstract_topic_matched": 0,
                    "title_only_topic_matched": 0,
                    "topic_filtered_out": filtered_out,
                    "topic_match_rate": match_rate,
                }

            if llm_candidate_count == 0:
                logger.info(
                    f"{journal} {subjournal_name}: "
                    f"TOPIC_KEYWORDS命中 {topic_matched} 篇，但全部已存在related CSV；"
                    f"跳过LLM，保留已有related结果"
                )
                return {
                    "reviewed": 0,
                    "saved": 0,
                    "related": 0,
                    "related_total": existing_related_before,
                    "already_related_skipped": already_related_skipped,
                    "llm_candidates": 0,
                    "review_failed": 0,
                    "prefiltered": topic_matched,
                    "title_abstract_topic_checked": title_abstract_topic_checked,
                    "title_only_topic_checked": title_only_topic_checked,
                    "title_only_reviewed": 0,
                    "title_abstract_topic_matched": title_abstract_topic_matched,
                    "title_only_topic_matched": title_only_topic_matched,
                    "topic_filtered_out": filtered_out,
                    "topic_match_rate": match_rate,
                }

            logger.info(
                f"{journal} {subjournal_name}: "
                f"TOPIC_KEYWORDS命中 {topic_matched} 篇；"
                f"其中已有related跳过={already_related_skipped}，"
                f"本轮LLM复核={llm_candidate_count}；"
                f"candidate_chunk_size={chunk_size}, "
                f"ollama_batch_size={getattr(agent, 'batch_size', '')}"
            )

            # ----------------------------------------------------------
            # Phase 2: review only TOPIC-matched candidate rows in chunks.
            # ----------------------------------------------------------
            llm_chunk = []

            def flush_llm_chunk():
                nonlocal reviewed
                nonlocal related
                nonlocal review_failed

                if not llm_chunk:
                    return

                current = list(llm_chunk)
                llm_chunk.clear()

                related_rows, failed_rows = (
                    self._llm_review_prefiltered_rows(
                        current,
                        agent,
                    )
                )

                reviewed += len(current)

                # Append only newly accepted Related/Borderline rows.
                # The set is updated immediately so duplicates inside the same
                # run are also suppressed.
                unique_related_rows = []
                for related_row in related_rows:
                    key = article_key(related_row)
                    if key and key in existing_related_keys:
                        continue
                    unique_related_rows.append(related_row)
                    if key:
                        existing_related_keys.add(key)

                related += self._append_result_rows_csv(
                    related_path,
                    unique_related_rows,
                )

                if self.config_manager.get(
                    "EXPORT_ON_LLM_FAILURE",
                    False,
                ):
                    review_failed += self._append_result_rows_csv(
                        failed_path,
                        failed_rows,
                    )
                else:
                    review_failed += len(failed_rows)

            with open(
                candidate_path,
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as candidate_handle:
                reader = csv.DictReader(candidate_handle)

                for row in reader:
                    llm_chunk.append(row)

                    if len(llm_chunk) >= chunk_size:
                        flush_llm_chunk()

                flush_llm_chunk()

        finally:
            if os.path.exists(candidate_path):
                try:
                    os.remove(candidate_path)
                except OSError:
                    pass

        # Never delete related_path here: it is cumulative across runs.
        # Remove only an empty current-run review_failed diagnostic file.
        if review_failed == 0 and os.path.exists(failed_path):
            os.remove(failed_path)

        filtered_out = total_rows - topic_matched
        match_rate = (
            (topic_matched / total_rows) * 100.0
            if total_rows
            else 0.0
        )

        logger.info(
            f"{journal} {subjournal_name}: "
            f"disk review summary all={total_rows}, "
            f"topic_checked_title_abstract={title_abstract_topic_checked}, "
            f"topic_checked_title_only={title_only_topic_checked}, "
            f"topic_keyword_matched={topic_matched}, "
            f"topic_filtered_out={filtered_out}, "
            f"topic_match_rate={match_rate:.2f}%, "
            f"topic_matched_title_abstract={title_abstract_topic_matched}, "
            f"topic_matched_title_only={title_only_topic_matched}, "
            f"already_related_skipped={already_related_skipped}, "
            f"llm_candidates={llm_candidate_count}, "
            f"llm_reviewed={reviewed}, "
            f"llm_related_new={related}, "
            f"related_total={len(existing_related_keys)}, "
            f"llm_failed={review_failed}, "
            f"saved_new={related}"
        )

        return {
            "reviewed": reviewed,
            "saved": related,
            "related": related,
            "related_total": len(existing_related_keys),
            "already_related_skipped": already_related_skipped,
            "llm_candidates": llm_candidate_count,
            "review_failed": review_failed,
            "prefiltered": topic_matched,
            "title_abstract_topic_checked": title_abstract_topic_checked,
            "title_only_topic_checked": title_only_topic_checked,
            "title_only_reviewed": title_only_topic_matched,
            "title_abstract_topic_matched": title_abstract_topic_matched,
            "title_only_topic_matched": title_only_topic_matched,
            "topic_filtered_out": filtered_out,
            "topic_match_rate": match_rate,
        }


    def _process_all_info_csv(
        self,
        all_info_path,
        journal,
        subjournal_name,
        agent,
        start_date_str,
        end_date_str,
    ):
        """Disk pipeline: expanded-title-gated abstract repair -> TOPIC -> cumulative LLM.

        Abstract repair:
            only empty-abstract rows whose titles hit expanded terms are repaired.

        LLM review:
            every TOPIC_KEYWORDS hit is reviewed unless its article_key is already
            present in the persistent related CSV.
        """
        repair_stats = self._repair_all_info_csv(
            all_info_path,
            journal,
            subjournal_name,
        )

        # Explicitly ensure old batch/list objects can be reclaimed before
        # opening the updated CSV for review.
        gc.collect()

        review_stats = (
            self._review_updated_all_info_csv(
                all_info_path,
                journal,
                subjournal_name,
                agent,
                start_date_str,
                end_date_str,
            )
        )

        result = dict(repair_stats)
        result.update(review_stats)
        return result

    def _stream_journal_to_all_info(
        self,
        journal,
        parser,
        journal_info,
        subjournal_name,
        agent,
        start_date,
        end_date,
    ):
        """Incrementally rescan one journal and append only unseen metadata.

        Existing all_info.csv is preserved. The journal is still rescanned on
        every run so newly published/indexed papers can be discovered.
        """
        topic_name = getattr(
            agent,
            "topic_name",
            "topic",
        )

        all_info_path = self._prepare_all_info_csv(
            journal,
            subjournal_name,
            topic_name,
        )

        existing_article_keys = self._load_article_keys_from_csv(
            all_info_path
        )
        existing_before = len(existing_article_keys)

        appended = 0
        skipped_existing = 0

        logger.info(
            f"{journal} {subjournal_name}: 增量metadata启动 "
            f"existing_article_keys={existing_before}; "
            f"将重新扫描期刊，仅追加新论文"
        )

        def persist_batch(
            batch,
            issue_title=None,
        ):
            nonlocal appended
            nonlocal skipped_existing

            new_count, skipped_count = (
                self._append_new_metadata_batch_to_all_info(
                    batch,
                    all_info_path,
                    subjournal_name,
                    existing_article_keys,
                    issue_title=issue_title,
                )
            )

            appended += new_count
            skipped_existing += skipped_count

            if new_count or skipped_count:
                logger.info(
                    f"{journal} {subjournal_name}: metadata增量批次 "
                    f"new={new_count}, existing_skipped={skipped_count}, "
                    f"known_total={len(existing_article_keys)}"
                )

        if hasattr(
            parser,
            "set_current_journal_info",
        ):
            parser.set_current_journal_info(
                journal_info
            )

        use_topic_stream = bool(
            getattr(
                parser,
                "should_use_topic_search",
                lambda: False,
            )()
        )

        if (
            use_topic_stream
            and hasattr(
                parser,
                "scrape_journal_topic_search_stream",
            )
        ):
            parser.scrape_journal_topic_search_stream(
                journal_name=subjournal_name,
                base_url=journal_info.get(
                    "link",
                    "",
                ),
                start_date=start_date,
                end_date=end_date,
                callback=persist_batch,
            )

        elif hasattr(
            parser,
            "scrape_journal_stream",
        ):
            parser.scrape_journal_stream(
                journal_name=subjournal_name,
                base_url=journal_info.get(
                    "link",
                    "",
                ),
                start_date=start_date,
                end_date=end_date,
                callback=persist_batch,
            )

        else:
            # Legacy safety fallback. Only this branch can build a full list.
            if use_topic_stream:
                papers = (
                    parser.scrape_journal_topic_search(
                        journal_name=subjournal_name,
                        base_url=journal_info.get(
                            "link",
                            "",
                        ),
                        start_date=start_date,
                        end_date=end_date,
                    )
                )
            else:
                papers = parser.scrape_journal(
                    journal_name=subjournal_name,
                    base_url=journal_info.get(
                        "link",
                        "",
                    ),
                    start_date=start_date,
                    end_date=end_date,
                )

            persist_batch(papers)
            del papers
            gc.collect()

        logger.info(
            f"{journal} {subjournal_name}: metadata增量扫描完成 "
            f"existing_before={existing_before}, "
            f"new_appended={appended}, "
            f"existing_skipped={skipped_existing}, "
            f"all_info_known_total={len(existing_article_keys)}"
        )

        return {
            "all_info_path": all_info_path,
            "existing_before": existing_before,
            "new_appended": appended,
            "existing_skipped": skipped_existing,
            "known_total": len(existing_article_keys),
        }

    def review_and_export_papers(self, papers, journal, subjournal_name, agent,
                                 start_date_str, end_date_str, export_format, issue_title=None):
        if not papers:
            return {
                "total_papers": 0,
                "candidate": 0,
                "skipped": 0,
                "reviewed": 0,
                "saved": 0,
                "related": 0,
                "review_failed": 0,
                "prefiltered": 0,
            }

        metadata_rows = []
        for paper in papers:
            item = {
                'title': paper.get('title', ''),
                'abstract': paper.get('abstract', ''),
                'date': paper.get('date'),
                'doi': paper.get('doi', ''),
                'link': paper.get('url', ''),
                'authors': paper.get('authors', ''),
                'journal': paper.get('journal', subjournal_name),
                'article_type': paper.get('article_type', paper.get('type', '')),
                'source': paper.get('source', ''),
                'quality_score': paper.get('quality_score', ''),
                'type': 'full'
            }
            if issue_title:
                item['issue'] = issue_title
            metadata_rows.append(item)

        topic_name = getattr(agent, 'topic_name', 'topic')
        candidate_count = len(metadata_rows)
        self.append_articles_to_named_csv(
            metadata_rows,
            "all_info.csv",
            folder_name=subjournal_name,
            topic_name=topic_name,
            platform_name=journal,
        )

        topic = TopicConfig(
            name=topic_name,
            keywords=list(getattr(agent, 'topic_keywords', []) or [])
        )
        if topic.keywords:
            repair_candidates = self._select_title_expanded_empty_abstract_rows(metadata_rows)
            # All standard platforms repair missing abstracts through doi_abstract.py.
            repair_count = self._repair_empty_abstract_candidates(repair_candidates, journal, subjournal_name)
            prefiltered_rows = [item for item in metadata_rows if article_matches_topic(item, topic)]
            related_rows, review_failed_rows = self._llm_review_prefiltered_rows(prefiltered_rows, agent)
            logger.info(
                f"{journal} {subjournal_name}: metadata keyword_filter={len(prefiltered_rows)}/{candidate_count}, "
                f"abstract_repaired={repair_count}, llm_related={len(related_rows)}, "
                f"llm_failed={len(review_failed_rows)}"
            )
        else:
            prefiltered_rows = []
            related_rows = []
            review_failed_rows = []
            logger.warning(f"{journal} {subjournal_name}: 未配置TOPIC_KEYWORDS，仅保存all_info.csv")

        related_rows = self._dedupe_rows_by_title(related_rows)
        saved_count = 0
        if related_rows:
            related_filename = f"{safe_path_name(topic_name)}_related_{start_date_str}_{end_date_str}.csv"
            self.append_articles_to_named_csv(
                related_rows,
                related_filename,
                folder_name=subjournal_name,
                topic_name=topic_name,
                platform_name=journal,
                overwrite=True,
            )
            saved_count = len(related_rows)
        else:
            related_filename = f"{safe_path_name(topic_name)}_related_{start_date_str}_{end_date_str}.csv"
            related_path = build_export_path(
                "csv",
                related_filename,
                folder_name=subjournal_name,
                topic_name=topic_name,
                platform_name=journal,
            )
            if os.path.exists(related_path):
                os.remove(related_path)

        logger.info(
            f"{journal} {subjournal_name}: metadata batch summary "
            f"all={candidate_count}, related={len(related_rows)}, saved={saved_count}"
        )
        return {
            "total_papers": len(papers),
            "candidate": candidate_count,
            "skipped": 0,
            "reviewed": len(prefiltered_rows),
            "saved": saved_count,
            "related": len(related_rows),
            "review_failed": len(review_failed_rows),
            "prefiltered": len(prefiltered_rows)
        }


    def _review_and_export_other_papers(
        self,
        papers,
        subjournal_name,
        agent,
        start_date_str,
        end_date_str,
        export_format,
    ):
        """OTHER-only review/export pipeline.

        Pipeline:
            Crossref ISSN metadata
            -> save ORIGINAL all_info.csv
            -> rows with abstract: title + abstract -> TOPIC_KEYWORDS
            -> rows without abstract:
                 sleep_expanded_terms TITLE coarse filter
                 -> DoiAbstractFetcher
                    Crossref DOI / Europe PMC / OpenAlex / Semantic Scholar
                 -> repair success: title + abstract -> TOPIC_KEYWORDS
                 -> repair failed: title-only -> TOPIC_KEYWORDS
            -> only TOPIC-matched rows -> LLM
            -> save related

        No publisher page is visited for OTHER abstract repair.
        Other journal types do not use this helper.
        """
        if not papers:
            return {
                "total_papers": 0,
                "candidate": 0,
                "skipped": 0,
                "reviewed": 0,
                "saved": 0,
                "related": 0,
                "review_failed": 0,
                "prefiltered": 0,
                "abstract_present": 0,
                "abstract_missing": 0,
                "expanded_title_matched": 0,
                "abstract_repair_attempted": 0,
                "abstract_repaired": 0,
                "title_only_reviewed": 0,
            }

        # 1) Normalize Crossref metadata.
        metadata_rows = []
        for paper in papers:
            item = {
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", ""),
                "date": paper.get("date"),
                "doi": paper.get("doi", ""),
                "link": paper.get("url", "") or paper.get("link", ""),
                "authors": paper.get("authors", ""),
                "journal": paper.get("journal", subjournal_name),
                "article_type": paper.get(
                    "article_type",
                    paper.get("type", ""),
                ),
                "source": paper.get("source", ""),
                "quality_score": paper.get("quality_score", ""),
                "type": "full",
            }
            metadata_rows.append(item)

        topic_name = getattr(agent, "topic_name", "topic")
        candidate_count = len(metadata_rows)

        # 2) Save raw/original Crossref metadata BEFORE repair.
        self.append_articles_to_named_csv(
            metadata_rows,
            "all_info.csv",
            folder_name=subjournal_name,
            topic_name=topic_name,
            platform_name="other",
        )

        # 3) Split by abstract availability.
        abstract_present_rows = [
            item for item in metadata_rows
            if str(item.get("abstract") or "").strip()
        ]
        empty_abstract_rows = [
            item for item in metadata_rows
            if not str(item.get("abstract") or "").strip()
        ]
        abstract_present = len(abstract_present_rows)
        abstract_missing = len(empty_abstract_rows)

        # 4) For missing abstracts only: TITLE coarse filter with expanded terms.
        expanded_terms = self._load_expanded_title_terms()
        if not expanded_terms:
            logger.warning(
                f"OTHER {subjournal_name}: sleep_expanded_terms.txt未加载；"
                f"空摘要记录不会进入DOI摘要补全"
            )
            repair_candidates = []
        else:
            repair_candidates = [
                item for item in empty_abstract_rows
                if self._text_matches_any_term(
                    str(item.get("title") or ""),
                    expanded_terms,
                )
            ]

        expanded_title_matched = len(repair_candidates)

        logger.info(
            f"OTHER {subjournal_name}: metadata_total={candidate_count}, "
            f"abstract_present={abstract_present}, "
            f"abstract_missing={abstract_missing}, "
            f"expanded_terms={len(expanded_terms)}, "
            f"expanded_title_matched={expanded_title_matched}"
        )

        # 5) OTHER-only DOI API abstract repair.
        repair_count, repair_failed_rows, source_counts = (
            self._repair_other_abstract_candidates(
                repair_candidates,
                subjournal_name,
            )
        )

        repaired_rows = [
            item for item in repair_candidates
            if str(item.get("abstract") or "").strip()
        ]

        # 6) TOPIC_KEYWORDS for ALL rows after repair.
        #    - original/repaired abstracts: title + abstract
        #    - repair failed / still empty: title only
        # No repair-failed row bypasses the TOPIC keyword gate.
        topic = TopicConfig(
            name=topic_name,
            keywords=list(getattr(agent, "topic_keywords", []) or []),
        )

        topic_input_rows = list(metadata_rows)

        if not topic.keywords:
            logger.warning(
                f"OTHER {subjournal_name}: 未配置TOPIC_KEYWORDS；"
                f"所有记录均不会进入LLM"
            )
            topic_matched_rows = []
        else:
            topic_matched_rows = []
            for item in topic_input_rows:
                abstract = str(item.get("abstract") or "").strip()
                if not article_matches_topic(item, topic):
                    continue
                item["review_input"] = (
                    "title_abstract" if abstract else "title_only"
                )
                topic_matched_rows.append(item)

        title_only_rows = [
            item for item in topic_matched_rows
            if not str(item.get("abstract") or "").strip()
        ]

        # De-duplicate before LLM.
        llm_rows = []
        seen = set()
        for item in topic_matched_rows:
            doi_key = str(item.get("doi") or "").strip().lower()
            title_key = " ".join(
                str(item.get("title") or "").lower().split()
            )
            key = ("doi", doi_key) if doi_key else ("title", title_key)
            if key in seen:
                continue
            seen.add(key)
            llm_rows.append(item)

        logger.info(
            f"OTHER {subjournal_name}: "
            f"topic_keyword_input={len(topic_input_rows)}, "
            f"topic_keyword_matched={len(topic_matched_rows)}, "
            f"title_only_llm={len(title_only_rows)}, "
            f"llm_total={len(llm_rows)}"
        )

        # 8) LLM review.
        related_rows, review_failed_rows = (
            self._llm_review_prefiltered_rows(
                llm_rows,
                agent,
            )
            if llm_rows
            else ([], [])
        )

        related_rows = self._dedupe_rows_by_title(related_rows)

        # 9) Save related results.
        related_filename = (
            f"{safe_path_name(topic_name)}_related_"
            f"{start_date_str}_{end_date_str}.csv"
        )

        saved_count = 0
        if related_rows:
            self.append_articles_to_named_csv(
                related_rows,
                related_filename,
                folder_name=subjournal_name,
                topic_name=topic_name,
                platform_name="other",
                overwrite=True,
            )
            saved_count = len(related_rows)
        else:
            related_path = build_export_path(
                "csv",
                related_filename,
                folder_name=subjournal_name,
                topic_name=topic_name,
                platform_name="other",
            )
            if os.path.exists(related_path):
                os.remove(related_path)

        logger.info(
            f"OTHER {subjournal_name}: pipeline summary "
            f"all={candidate_count}, "
            f"abstract_present={abstract_present}, "
            f"abstract_missing={abstract_missing}, "
            f"expanded_title_matched={expanded_title_matched}, "
            f"abstract_repaired={repair_count}, "
            f"abstract_repair_failed={len(repair_failed_rows)}, "
            f"abstract_sources={source_counts}, "
            f"topic_keyword_matched={len(topic_matched_rows)}, "
            f"title_only_llm={len(title_only_rows)}, "
            f"llm_reviewed={len(llm_rows)}, "
            f"llm_related={len(related_rows)}, "
            f"llm_failed={len(review_failed_rows)}, "
            f"saved={saved_count}"
        )

        return {
            "total_papers": len(papers),
            "candidate": candidate_count,
            "skipped": 0,
            "reviewed": len(llm_rows),
            "saved": saved_count,
            "related": len(related_rows),
            "review_failed": len(review_failed_rows),
            "prefiltered": len(topic_matched_rows),
            "abstract_present": abstract_present,
            "abstract_missing": abstract_missing,
            "expanded_title_matched": expanded_title_matched,
            "abstract_repair_attempted": expanded_title_matched,
            "abstract_repaired": repair_count,
            "abstract_repair_failed": len(repair_failed_rows),
            "title_only_reviewed": len(title_only_rows),
            "abstract_sources": source_counts,
        }

    def _dedupe_rows_by_title(self, rows):
        deduped = []
        seen_titles = set()
        for item in rows or []:
            title_key = " ".join(str(item.get("title") or "").lower().split())
            if title_key:
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
            deduped.append(item)
        return deduped

    def _select_title_expanded_empty_abstract_rows(self, rows):
        terms = self._load_expanded_title_terms()
        if not terms:
            return []
        candidates = []
        for item in rows:
            if str(item.get("abstract") or "").strip():
                continue
            title = str(item.get("title") or "")
            if self._text_matches_any_term(title, terms):
                candidates.append(item)
        return candidates

    def _load_expanded_title_terms(self):
        if self._expanded_title_terms is not None:
            return self._expanded_title_terms
        configured = self.config_manager.get("EXPANDED_TITLE_TERMS_PATH")
        path = Path(configured) if configured else BASE_DIR / "sleep_expanded_terms.txt"
        terms = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    value = line.strip()
                    if not value or value.startswith("#"):
                        continue
                    terms.append(value)
        except Exception as e:
            logger.warning(f"expanded title terms load failed: {path} - {e}")
        self._expanded_title_terms = terms
        return terms

    def _text_matches_any_term(self, text, terms):
        lowered = str(text or "").lower()
        if not lowered:
            return False
        for term in terms:
            value = str(term or "").strip().lower()
            if not value:
                continue
            pattern = r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(value)
            if re.search(pattern, lowered, flags=re.I):
                return True
        return False

    def _llm_review_prefiltered_rows(self, rows, agent):
        if not rows:
            return [], []
        for index, item in enumerate(rows, start=1):
            item["id"] = str(index)
        contents = [
            {"id": item["id"], "title": item.get("title", ""), "abstract": item.get("abstract", "")}
            for item in rows
        ]
        llm_results = agent.batch_analyze_papers_in_batches_concurrent(contents)
        result_map = {str(result.get("id")): result for result in llm_results or []}
        related_rows = []
        review_failed_rows = []
        for item in rows:
            result = result_map.get(str(item.get("id")))
            if not result or result.get("judgment") in ("Unable to determine", "Error"):
                item["reason"] = getattr(agent, "last_error_reason", "") or (result or {}).get("explanation", "LLM复核失败")
                item["review_status"] = "review_failed"
                item["is_related"] = False
                review_failed_rows.append(item)
            elif result.get("is_ai_related", False):
                item["reason"] = result.get("explanation", "")
                item["review_status"] = "related"
                item["is_related"] = True
                related_rows.append(item)
            else:
                item["review_status"] = "unrelated"
                item["is_related"] = False
        return related_rows, review_failed_rows

    def _repair_other_abstract_candidates(self, candidates, subjournal_name):
        """OTHER-only DOI API abstract repair with bounded parallel workers."""
        parser = self.parsers.get("other")
        if not parser or not hasattr(
            parser,
            "repair_abstract_by_doi",
        ):
            logger.warning(
                f"OTHER {subjournal_name}: parser缺少repair_abstract_by_doi，"
                f"跳过DOI API摘要补全"
            )
            return 0, list(candidates or []), {}

        workers, repair_batch_size, _ = (
            self._abstract_repair_parallel_config()
        )

        if (
            workers > 1
            and not getattr(
                parser,
                "thread_safe_abstract_repair",
                False,
            )
        ):
            logger.warning(
                f"OTHER {subjournal_name}: parser未声明线程安全摘要补全，"
                f"自动降级为单线程"
            )
            workers = 1

        work_items = [
            item
            for item in (candidates or [])
            if not str(item.get("abstract") or "").strip()
        ]

        repaired_count = 0
        failed_rows = []
        source_counts = {}

        logger.info(
            f"OTHER {subjournal_name}: DOI API并行补摘要启动 "
            f"attempted={len(work_items)}, "
            f"workers={workers}, batch_size={repair_batch_size}"
        )

        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="doi-abstract",
        ) as executor:
            for offset in range(
                0,
                len(work_items),
                repair_batch_size,
            ):
                batch = work_items[
                    offset:offset + repair_batch_size
                ]

                repaired_batch = self._parallel_repair_rows(
                    batch,
                    "other",
                    subjournal_name,
                    mode="doi_only",
                    executor=executor,
                )

                for item, repaired in zip(
                    batch,
                    repaired_batch,
                ):
                    doi = str(
                        item.get("doi") or ""
                    ).strip()

                    if not doi:
                        item["abstract_repair_status"] = "missing_doi"
                        failed_rows.append(item)
                        continue

                    repair_error = str(
                        repaired.get("_repair_error") or ""
                    ).strip()
                    if repair_error:
                        logger.warning(
                            f"OTHER {subjournal_name}: DOI API abstract "
                            f"repair failed doi={doi}: {repair_error}"
                        )
                        item["abstract_repair_status"] = "error"
                        failed_rows.append(item)
                        continue

                    abstract = str(
                        repaired.get("abstract") or ""
                    ).strip()

                    if not abstract:
                        item["abstract_repair_status"] = "not_found"
                        failed_rows.append(item)
                        continue

                    item["abstract"] = abstract
                    item["abstract_repaired"] = True
                    item["abstract_repair_status"] = "repaired"

                    abstract_source = str(
                        repaired.get("abstract_source")
                        or repaired.get("source")
                        or ""
                    ).strip()

                    if abstract_source:
                        item["abstract_source"] = abstract_source
                        source_counts[abstract_source] = (
                            source_counts.get(abstract_source, 0) + 1
                        )

                    for field in (
                        "title",
                        "date",
                        "doi",
                        "link",
                        "authors",
                        "journal",
                    ):
                        if str(item.get(field) or "").strip():
                            continue
                        value = repaired.get(field)
                        if value is not None and str(value).strip():
                            item[field] = value

                    repaired_count += 1

        logger.info(
            f"OTHER {subjournal_name}: DOI API abstract repair "
            f"attempted={len(work_items)}, workers={workers}, "
            f"repaired={repaired_count}, "
            f"not_found={len(failed_rows)}, "
            f"sources={source_counts}"
        )
        return repaired_count, failed_rows, source_counts

    def _repair_empty_abstract_candidates(
        self,
        candidates,
        journal,
        subjournal_name,
    ):
        """Parallel DOI-only repair for legacy/non-disk platform flows."""
        parser = self.parsers.get(journal)
        if not parser or not hasattr(
            parser,
            "repair_abstract_by_doi",
        ):
            logger.warning(
                f"{journal} {subjournal_name}: parser缺少repair_abstract_by_doi，"
                f"跳过DOI API摘要补全"
            )
            return 0

        workers, repair_batch_size, _ = (
            self._abstract_repair_parallel_config()
        )

        if (
            workers > 1
            and not getattr(
                parser,
                "thread_safe_abstract_repair",
                False,
            )
        ):
            workers = 1

        work_items = [
            item
            for item in (candidates or [])
            if not str(item.get("abstract") or "").strip()
        ]

        repaired_count = 0
        source_counts = {}

        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="doi-abstract",
        ) as executor:
            for offset in range(
                0,
                len(work_items),
                repair_batch_size,
            ):
                batch = work_items[
                    offset:offset + repair_batch_size
                ]

                repaired_batch = self._parallel_repair_rows(
                    batch,
                    journal,
                    subjournal_name,
                    mode="doi_only",
                    executor=executor,
                )

                for item, repaired in zip(
                    batch,
                    repaired_batch,
                ):
                    repair_error = str(
                        repaired.get("_repair_error") or ""
                    ).strip()
                    if repair_error:
                        logger.warning(
                            f"{journal} {subjournal_name}: DOI API abstract "
                            f"repair failed doi={item.get('doi', '')}: "
                            f"{repair_error}"
                        )
                        continue

                    abstract = str(
                        repaired.get("abstract") or ""
                    ).strip()

                    if not abstract:
                        continue

                    item["abstract"] = abstract
                    item["abstract_repaired"] = True
                    item["abstract_repair_status"] = "repaired"

                    source = str(
                        repaired.get("abstract_source")
                        or repaired.get("source")
                        or ""
                    ).strip()

                    if source:
                        item["abstract_source"] = source
                        source_counts[source] = (
                            source_counts.get(source, 0) + 1
                        )

                    for field in (
                        "title",
                        "date",
                        "doi",
                        "link",
                        "authors",
                        "journal",
                    ):
                        if str(item.get(field) or "").strip():
                            continue
                        value = repaired.get(field)
                        if value is not None and str(value).strip():
                            item[field] = value

                    repaired_count += 1

        logger.info(
            f"{journal} {subjournal_name}: DOI API abstract repair "
            f"attempted={len(work_items)}, workers={workers}, "
            f"repaired={repaired_count}, sources={source_counts}"
        )
        return repaired_count

    def run_topic_crawl(
        self,
        journal_csv_path,
        start_date_str,
        end_date_str,
        export_format="xlsx",
        target_subjournal=None,
        target_journals=None,
    ):
        """Execute the unified low-memory topic crawler.

        For every platform:
            parser/Crossref stream
            -> append all_info.csv
            -> repair abstracts by DOI while rewriting all_info.csv
            -> atomically replace all_info.csv
            -> reopen updated all_info.csv
            -> chunked TOPIC + LLM
            -> append result CSVs

        No platform keeps the complete journal metadata corpus in main.py.
        """
        logger.info("=" * 60)
        logger.info(
            f"CSV 文件: {journal_csv_path}"
        )
        logger.info(
            f"时间范围: {start_date_str} 至 {end_date_str}"
        )
        logger.info(
            f"导出格式: {export_format}"
        )
        logger.info("=" * 60)

        journal_lists, skipped = (
            load_supported_journals_from_csv(
                journal_csv_path
            )
        )

        journals = [
            name
            for name in PLATFORM_FAMILIES
            if journal_lists.get(name)
        ]

        if target_journals:
            requested = {
                str(item).strip().lower()
                for item in re.split(
                    r"[,;|\s]+",
                    str(target_journals),
                )
                if str(item).strip()
            }

            journals = [
                name
                for name in journals
                if name.lower() in requested
            ]

            logger.info(
                "已按RUN_JOURNALS过滤平台: %s",
                ", ".join(journals)
                if journals
                else "无匹配",
            )

        logger.info(
            "CSV平台期刊统计: "
            + ", ".join(
                f"{journal}={len(journal_lists[journal])}"
                for journal in PLATFORM_FAMILIES
            )
        )

        if skipped:
            logger.info(
                "OTHER平台期刊交给NewJournalParser处理: %s 个",
                len(skipped),
            )

        if not journals:
            logger.error(
                "CSV中没有当前解析器支持的平台期刊"
            )
            return {}

        results = {}
        start_date = datetime.strptime(
            start_date_str,
            "%Y-%m-%d",
        )
        end_date = datetime.strptime(
            end_date_str,
            "%Y-%m-%d",
        )

        for journal in journals:
        # try:
            logger.info(
                f"初始化 {journal.upper()} 期刊组件..."
            )

            self.initialize_journal(
                journal
            )

            parser = self.parsers[journal]
            agent = self.agents[journal]

            journal_list = list(
                journal_lists[journal]
            )

            if target_subjournal:
                journal_list = [
                    item
                    for item in journal_list
                    if item["name"]
                    == target_subjournal
                ]

                if not journal_list:
                    logger.error(
                        f"未找到指定子刊: {target_subjournal}"
                    )
                    results[journal] = {
                        "error": (
                            f"子刊不存在: "
                            f"{target_subjournal}"
                        )
                    }
                    continue

                logger.info(
                    f"已过滤到子刊: "
                    f"{target_subjournal}"
                )

            total_papers = 0
            total_related = 0
            total_review_failed = 0
            total_subjournals = len(
                journal_list
            )
            failed_subjournals = []

            for idx, journal_info in enumerate(
                journal_list,
                start=1,
            ):
                subjournal_name = (
                    journal_info["name"]
                )

                logger.info(
                    f"[{idx}/{total_subjournals}] "
                    f"处理子刊: {subjournal_name}"
                )

                csv_link = (
                    journal_info.get(
                        "csv_link"
                    )
                    or journal_info.get(
                        "source_row",
                        {},
                    ).get("期刊URL")
                )
                parser_link = (
                    journal_info.get("link")
                )

                if (
                    csv_link
                    and parser_link
                    and csv_link != parser_link
                ):
                    logger.info(
                        f"{journal} "
                        f"{subjournal_name}: "
                        f"CSV URL={csv_link} "
                        f"-> Parser URL={parser_link}"
                    )

                try:
                    stream_stats = (
                        self._stream_journal_to_all_info(
                            journal=journal,
                            parser=parser,
                            journal_info=journal_info,
                            subjournal_name=(
                                subjournal_name
                            ),
                            agent=agent,
                            start_date=start_date,
                            end_date=end_date,
                        )
                    )
                    all_info_path = stream_stats["all_info_path"]
                    candidate_count = stream_stats["known_total"]
                    new_article_count = stream_stats["new_appended"]

                    # Even when no NEW paper is discovered, existing TOPIC hits
                    # that are not yet in related CSV must be re-reviewed.
                    if (
                        candidate_count <= 0
                        or not os.path.exists(all_info_path)
                        or os.path.getsize(all_info_path) == 0
                    ):
                        logger.info(
                            f"{journal} "
                            f"{subjournal_name}: "
                            f"all_info.csv无可处理论文"
                        )
                        continue

                    # At this point Crossref batch objects are no longer
                    # needed; all processing continues from the CSV.
                    gc.collect()

                    counts = (
                        self._process_all_info_csv(
                            all_info_path=(
                                all_info_path
                            ),
                            journal=journal,
                            subjournal_name=(
                                subjournal_name
                            ),
                            agent=agent,
                            start_date_str=(
                                start_date_str
                            ),
                            end_date_str=(
                                end_date_str
                            ),
                        )
                    )

                    total_papers += (
                        candidate_count
                    )
                    total_related += (
                        counts.get(
                            "related",
                            0,
                        )
                    )
                    total_review_failed += (
                        counts.get(
                            "review_failed",
                            0,
                        )
                    )

                    logger.info(
                        f"{journal} "
                        f"{subjournal_name}: "
                        f"disk pipeline complete "
                        f"all_info_total={candidate_count}, "
                        f"new_articles={new_article_count}, "
                        f"abstract_missing="
                        f"{counts.get('abstract_missing', 0)}, "
                        f"expanded_title_matched="
                        f"{counts.get('expanded_title_matched', 0)}, "
                        f"publisher_repaired="
                        f"{counts.get('publisher_repaired', 0)}, "
                        f"publisher_antibot="
                        f"{counts.get('publisher_antibot', 0)}, "
                        f"doi_repaired="
                        f"{counts.get('doi_abstract_repaired', 0)}, "
                        f"abstract_repaired="
                        f"{counts.get('abstract_repaired', 0)}, "
                        f"topic_keyword_matched="
                        f"{counts.get('prefiltered', 0)}, "
                        f"title_only_topic_checked="
                        f"{counts.get('title_only_topic_checked', 0)}, "
                        f"title_only_llm="
                        f"{counts.get('title_only_reviewed', 0)}, "
                        f"reviewed="
                        f"{counts.get('reviewed', 0)}, "
                        f"related="
                        f"{counts.get('related', 0)}, "
                        f"review_failed="
                        f"{counts.get('review_failed', 0)}"
                    )

                except Exception as exc:
                    failed_subjournals.append(
                        subjournal_name
                    )
                    logger.warning(
                        f"子刊 {subjournal_name} "
                        f"处理失败: {exc}"
                    )
                    continue

            results[journal] = {
                "total_papers": total_papers,
                "related": total_related,
                "review_failed": (
                    total_review_failed
                ),
                "successful_subjournals": (
                    total_subjournals
                    - len(failed_subjournals)
                ),
                "total_subjournals": (
                    total_subjournals
                ),
                "failed_subjournals": (
                    failed_subjournals
                ),
            }

            # except Exception as exc:
            #     logger.error(
            #         f"{journal.upper()} "
            #         f"期刊处理失败: {exc}"
            #     )
            #     results[journal] = {
            #         "error": str(exc)
            #     }

        topic_name = self.config_manager.get(
            "TOPIC_NAME",
            "topic",
        )

        self.print_summary(
            results,
            topic_name=topic_name,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            export_format=export_format,
        )

        return results

    def _read_export_count(self, filepath):
        if not os.path.exists(filepath):
            return 0
        try:
            if filepath.endswith(".csv"):
                return len(pd.read_csv(filepath, encoding="utf-8-sig")) if pd is not None else 0
            if filepath.endswith(".xlsx"):
                return len(pd.read_excel(filepath)) if pd is not None else 0
            if filepath.endswith(".json"):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return len(data) if isinstance(data, list) else 0
        except Exception as e:
            logger.warning(f"读取统计文件失败，跳过: {filepath} - {e}")
        return 0

    def _summary_from_export_files(self, topic_name, start_date_str, end_date_str, export_format):
        topic_dir = EXPORTS_DIR / safe_path_name(topic_name)
        if not topic_dir.exists():
            return {}
        related_name = f"{safe_path_name(topic_name)}_related_{start_date_str}_{end_date_str}.{export_format}"
        failed_name = f"{safe_path_name(topic_name)}_review_failed_{start_date_str}_{end_date_str}.{export_format}"
        summary = {}
        for platform_dir in topic_dir.iterdir():
            if not platform_dir.is_dir():
                continue
            platform = platform_dir.name.lower()
            platform_summary = summary.setdefault(platform, {
                "related": 0,
                "review_failed": 0,
                "subjournals_with_related": 0,
                "subjournals_with_review_failed": 0,
            })
            for subjournal_dir in platform_dir.iterdir():
                if not subjournal_dir.is_dir():
                    continue
                related_path = subjournal_dir / related_name
                failed_path = subjournal_dir / failed_name
                related_count = self._read_export_count(str(related_path))
                failed_count = self._read_export_count(str(failed_path))
                platform_summary["related"] += related_count
                platform_summary["review_failed"] += failed_count
                if related_count:
                    platform_summary["subjournals_with_related"] += 1
                if failed_count:
                    platform_summary["subjournals_with_review_failed"] += 1
        return summary

    def print_summary(self, results, topic_name=None, start_date_str=None, end_date_str=None, export_format='csv'):
        """打印爬取总结"""
        logger.info("="*80)
        logger.info("主题爬取完成总结")
        logger.info("="*80)
        logger.info(f"{'期刊':<12} {'抓取总数':<12} {'相关':<12} {'复核失败':<12} {'子刊成功':<12} {'状态':<12}")
        logger.info("-"*88)

        total_papers = total_related = total_failed = 0
        success_count = 0

        for journal, result in results.items():
            if 'error' in result:
                logger.info(f"{journal.upper():<12} {'--':<12} {'--':<12} {'--':<12} {'--':<12} {'失败':<12}")
                logger.info(f"  错误: {result['error']}")
            else:
                papers = result.get('total_papers', 0)
                related = result.get('related', 0)
                rev_failed = result.get('review_failed', 0)
                succ = result.get('successful_subjournals', 0)
                total_subs = result.get('total_subjournals', 0)
                status = "成功" if not result.get('failed_subjournals') else "部分成功"
                logger.info(f"{journal.upper():<12} {papers:<12} {related:<12} {rev_failed:<12} {succ}/{total_subs:<12} {status:<12}")
                if result.get('failed_subjournals'):
                    logger.info(f"  失败子刊: {', '.join(result['failed_subjournals'])}")
                total_papers += papers
                total_related += related
                total_failed += rev_failed
                success_count += 1

        logger.info("-"*88)
        logger.info(f"{'总计':<12} {total_papers:<12} {total_related:<12} {total_failed:<12} {'--':<12} {success_count}/{len(results)}成功")
        logger.info("="*80)

        if topic_name and start_date_str and end_date_str:
            file_summary = self._summary_from_export_files(topic_name, start_date_str, end_date_str, export_format)
            if file_summary:
                logger.info("="*80)
                logger.info("按导出文件统计 related/review_failed（包含历史已保存结果）")
                logger.info("="*80)
                logger.info(f"{'期刊':<12} {'related文件论文数':<18} {'review_failed论文数':<20} {'有related子刊':<14}")
                logger.info("-"*88)
                file_related_total = 0
                file_failed_total = 0
                for platform in sorted(file_summary):
                    item = file_summary[platform]
                    file_related_total += item["related"]
                    file_failed_total += item["review_failed"]
                    logger.info(
                        f"{platform.upper():<12} {item['related']:<18} "
                        f"{item['review_failed']:<20} {item['subjournals_with_related']:<14}"
                    )
                logger.info("-"*88)
                logger.info(f"{'总计':<12} {file_related_total:<18} {file_failed_total:<20} {'--':<14}")
                logger.info("="*80)

        if self.saved_files:
            logger.info("保存的文件:")
            for fp in self.saved_files:
                logger.info(f"  - {fp}")

    def cleanup(self):
        for parser in self.parsers.values():
            if hasattr(parser, 'cleanup'):
                parser.cleanup()
        for agent in self.agents.values():
            if hasattr(agent, 'close'):
                agent.close()


def main():
    # 1. 解析命令行参数（全部变为可选）
    parser = argparse.ArgumentParser(description='主题爬虫（从config读取参数）')
    parser.add_argument('--journal-csv', help='期刊列表CSV文件路径（可选，默认使用config中的RUN_JOURNAL_CSV）')
    parser.add_argument('--subjournal', help='指定单个子刊名称（可选）')
    parser.add_argument('--journals', help='指定平台，例如 science 或 nature,science（可选）')
    parser.add_argument('--start-date', help='开始日期 YYYY-MM-DD（可选，默认使用config中的RUN_START_DATE）')
    parser.add_argument('--end-date', help='结束日期 YYYY-MM-DD（可选，默认使用config中的RUN_END_DATE）')
    parser.add_argument('--format', choices=['xlsx', 'csv', 'json'], help='导出格式（可选，默认使用config中的RUN_FORMAT）')
    args = parser.parse_args()

    # 2. 加载配置
    config_mgr = ConfigManager()
    config = config_mgr.config  # 直接获取整个配置字典

    # 3. 从配置中读取参数，命令行参数优先（如果有）
    run_config = resolve_run_config(args, config)

    # 4. 校验必需参数是否存在
    missing = []
    if not run_config.journal_csv:
        missing.append('RUN_JOURNAL_CSV')
    if not run_config.start_date:
        missing.append('RUN_START_DATE')
    if not run_config.end_date:
        missing.append('RUN_END_DATE')
    if missing:
        logger.error(f"配置文件缺少以下必需参数: {', '.join(missing)}，请在config.yaml中设置或通过命令行传入")
        return 1

    # 5. 启动爬虫
    crawler = CrawlerSystem()
    # try:
    results = crawler.run_topic_crawl(
        journal_csv_path=run_config.journal_csv,
        start_date_str=run_config.start_date,
        end_date_str=run_config.end_date,
        export_format=run_config.export_format,
        target_subjournal=run_config.subjournal,  # 子刊仍可选
        target_journals=run_config.journals,
    )
    if any('error' in r for r in results.values()):
        return 1
    return 0
    # except KeyboardInterrupt:
    #     logger.info("用户中断")
    #     return 1
    # except Exception as e:
    #     logger.error(f"系统异常: {e}")
    #     return 1
    # finally:
    #     crawler.cleanup()

if __name__ == '__main__':
    sys.exit(main())
