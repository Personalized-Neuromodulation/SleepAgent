from __future__ import annotations

import math
import os
from typing import Any


class EmbeddingError(RuntimeError):
    pass


class LocalMiniLMEmbeddingClient:
    """Local MiniLM embeddings loaded from the local HuggingFace cache."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        *,
        local_files_only: bool = True,
        device: str | None = "cpu",
        cache_folder: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.local_files_only = local_files_only
        self.device = device
        self.cache_folder = cache_folder
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            if self.local_files_only:
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                os.environ.setdefault("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
                os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.expanduser("~/.cache/sentence_transformers"))
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:  # pragma: no cover
                raise EmbeddingError("sentence-transformers is required for local MiniLM embeddings") from exc
            kwargs: dict[str, Any] = {"local_files_only": self.local_files_only}
            cache_folder = self.cache_folder or os.getenv("SENTENCE_TRANSFORMERS_HOME")
            if cache_folder:
                kwargs["cache_folder"] = cache_folder
            if self.device:
                kwargs["device"] = self.device
            try:
                self._model = SentenceTransformer(self.model_name, **kwargs)
            except Exception as exc:  # pragma: no cover
                if self.local_files_only:
                    raise EmbeddingError(
                        f"Failed to load local embedding model '{self.model_name}'. "
                        "The model must exist in the local cache because online HuggingFace access is disabled."
                    ) from exc
                raise
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]


def dense_cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
