from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="PAPER_RAG_", extra="ignore"
    )

    database_url: str = "postgresql://paper_rag:paper_rag_password@localhost:5432/paper_rag"
    paper_root: Path = Path(r"D:\crawler2025\crawler_light\exports_811\sleep")
    canonical_root: Path = Path(r"D:\crawler2025\crawler_light\exports_811\sleep_rag_canonical")
    grobid_url: str = "http://localhost:8070"

    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_device: str = "cuda"
    embedding_batch_size: int = 16

    parent_chunk_tokens: int = 1200
    child_chunk_tokens: int = 550
    child_chunk_overlap: int = 80

    reranker_model: str | None = None
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3:14b"

    request_timeout_seconds: float = Field(default=180.0, ge=10)
    source_csv: Path = Path(r"D:\crawler2025\crawler_light\download_results.csv")
    ingest_limit: int | None = 20
    ingest_force: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8000


YAML_FIELDS = {
    "database": {"url": "database_url"},
    "paths": {
        "paper_root": "paper_root",
        "canonical_root": "canonical_root",
        "source_csv": "source_csv",
    },
    "parsing": {
        "grobid_url": "grobid_url",
        "request_timeout_seconds": "request_timeout_seconds",
    },
    "embedding": {
        "model": "embedding_model",
        "dimension": "embedding_dimension",
        "device": "embedding_device",
        "batch_size": "embedding_batch_size",
    },
    "chunking": {
        "parent_tokens": "parent_chunk_tokens",
        "child_tokens": "child_chunk_tokens",
        "child_overlap": "child_chunk_overlap",
    },
    "ingestion": {"limit": "ingest_limit", "force": "ingest_force"},
    "retrieval": {"reranker_model": "reranker_model"},
    "llm": {"base_url": "llm_base_url", "api_key": "llm_api_key", "model": "llm_model"},
    "api": {"host": "api_host", "port": "api_port"},
}


def _flatten_yaml(payload: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for section, mapping in YAML_FIELDS.items():
        section_data = payload.get(section, {})
        if section_data is None:
            continue
        if not isinstance(section_data, dict):
            raise ValueError(f"config.yaml中的{section}必须是映射")
        for yaml_name, field_name in mapping.items():
            if yaml_name in section_data:
                values[field_name] = section_data[yaml_name]
    return values


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or Path(os.environ.get("PAPER_RAG_CONFIG", "config.yaml"))
    yaml_values: dict[str, Any] = {}
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"配置文件根节点必须是映射: {path}")
        yaml_values = _flatten_yaml(payload)

    # 真正的环境变量优先于YAML；未写入YAML的字段仍可由.env或默认值提供。
    for field_name in Settings.model_fields:
        if f"PAPER_RAG_{field_name.upper()}" in os.environ:
            yaml_values.pop(field_name, None)
    return Settings(**yaml_values)


settings = load_settings()
