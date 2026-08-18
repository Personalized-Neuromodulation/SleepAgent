from __future__ import annotations

from collections.abc import Sequence

import numpy as np


class EmbeddingService:
    def __init__(self, model_name: str, device: str = "cuda", batch_size: int = 16):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    @property
    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def encode_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        if hasattr(self.model, "encode_document"):
            return self.model.encode_document(
                list(texts),
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=True,
            ).astype(np.float32)
        return self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        ).astype(np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        if hasattr(self.model, "encode_query"):
            return self.model.encode_query(
                text,
                normalize_embeddings=True,
                convert_to_numpy=True,
            ).astype(np.float32)
        return self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

