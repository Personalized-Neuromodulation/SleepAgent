from __future__ import annotations

import math
from typing import Any


class EmbeddingError(RuntimeError):
    pass


class LocalMiniLMEmbeddingClient:
    """Local MiniLM embeddings; never calls DeepSeek or an online embedding API."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:  # pragma: no cover
                raise EmbeddingError("sentence-transformers is required for local MiniLM embeddings") from exc
            self._model = SentenceTransformer(self.model_name)
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
