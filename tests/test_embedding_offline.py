import os
import sys
import types

from sleep_ai_scientist.hypothesis.agents.embedding import LocalMiniLMEmbeddingClient


def test_local_minilm_embedding_loads_sentence_transformer_offline(monkeypatch, tmp_path):
    captured = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):
            captured["model_name"] = model_name
            captured["kwargs"] = kwargs

        def encode(self, texts, normalize_embeddings=True):
            captured["texts"] = texts
            captured["normalize_embeddings"] = normalize_embeddings
            return [[0.1, 0.2, 0.3] for _ in texts]

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    client = LocalMiniLMEmbeddingClient("sentence-transformers/all-MiniLM-L6-v2", cache_folder=str(tmp_path), device="cpu")
    vectors = client.embed(["insomnia thalamocortical slow wave"])

    assert vectors == [[0.1, 0.2, 0.3]]
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert captured["model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert captured["kwargs"]["local_files_only"] is True
    assert captured["kwargs"]["cache_folder"] == str(tmp_path)
    assert captured["kwargs"]["device"] == "cpu"
    assert captured["normalize_embeddings"] is True
