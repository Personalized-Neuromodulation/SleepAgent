import json

from sleep_ai_scientist.grounding.retrieval import retrieve, tfidf_retrieve
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_keyword_retrieval_returns_ranked_hits():
    records = [
        LiteratureRecord(paper_id="toy001", title="Thalamocortical insomnia", abstract="Slow wave disruption"),
        LiteratureRecord(paper_id="toy002", title="Circadian rhythm", abstract="Animal sleep timing"),
    ]
    hits = retrieve("thalamocortical insomnia", records, top_k=2)
    assert hits
    assert hits[0].paper_id == "toy001"


def test_tfidf_fallback_returns_hits():
    records = [
        LiteratureRecord(paper_id="toy001", title="Insomnia EEG", abstract="Slow wave disruption"),
        LiteratureRecord(paper_id="toy003", title="Diffusion MRI", abstract="White matter integrity in sleep quality"),
    ]
    hits = tfidf_retrieve("white matter integrity", records, top_k=1)
    assert hits[0].paper_id == "toy003"


def test_embedding_disabled_uses_keyword_strategy_without_loading_model(monkeypatch):
    records = [
        LiteratureRecord(paper_id="p1", title="Insomnia thalamocortical slow wave", abstract=""),
        LiteratureRecord(paper_id="p2", title="Circadian animal model", abstract=""),
    ]

    def fail_if_loaded(*_args, **_kwargs):
        raise AssertionError("embedding model should not load when enabled=false")

    monkeypatch.setattr("sleep_ai_scientist.grounding.retrieval.LocalMiniLMEmbeddingClient", fail_if_loaded)

    hits = retrieve(
        "insomnia thalamocortical",
        records,
        top_k=1,
        embedding_config={"provider": "local_minilm", "model": "sentence-transformers/all-MiniLM-L6-v2", "enabled": False},
    )

    assert hits[0].paper_id == "p1"


def test_embedding_enabled_uses_local_minilm_dense_similarity(monkeypatch):
    records = [
        LiteratureRecord(paper_id="keyword_hit", title="Insomnia insomnia insomnia", abstract=""),
        LiteratureRecord(paper_id="semantic_hit", title="Thalamic coupling and sleep continuity", abstract=""),
    ]

    class FakeEmbeddingClient:
        def __init__(self, model_name, **kwargs):
            self.model_name = model_name

        def embed(self, texts):
            assert self.model_name == "sentence-transformers/all-MiniLM-L6-v2"
            vectors = []
            for text in texts:
                if text == "insomnia":
                    vectors.append([1.0, 0.0])
                elif text.startswith("Insomnia insomnia insomnia"):
                    vectors.append([0.1, 0.9])
                elif text.startswith("Thalamic coupling and sleep continuity"):
                    vectors.append([0.95, 0.05])
                else:
                    raise AssertionError(f"unexpected text: {text}")
            return vectors

    monkeypatch.setattr("sleep_ai_scientist.grounding.retrieval.LocalMiniLMEmbeddingClient", FakeEmbeddingClient)

    hits = retrieve(
        "insomnia",
        records,
        top_k=2,
        embedding_config={"provider": "local_minilm", "model": "sentence-transformers/all-MiniLM-L6-v2", "enabled": True},
    )

    assert [hit.paper_id for hit in hits] == ["semantic_hit", "keyword_hit"]


def test_embedding_retrieval_prints_and_writes_progress_log(monkeypatch, tmp_path, capsys):
    records = [
        LiteratureRecord(paper_id="p1", title="Insomnia EEG", abstract="slow wave"),
        LiteratureRecord(paper_id="p2", title="Sleep quality DTI", abstract="white matter"),
    ]

    class FakeEmbeddingClient:
        def __init__(self, model_name, **kwargs):
            self.model_name = model_name

        def embed(self, texts):
            assert len(texts) == 3
            return [[1.0, 0.0], [0.8, 0.2], [0.0, 1.0]]

    monkeypatch.setattr("sleep_ai_scientist.grounding.retrieval.LocalMiniLMEmbeddingClient", FakeEmbeddingClient)
    log_file = tmp_path / "embedding.log"

    hits = retrieve(
        "insomnia slow wave",
        records,
        top_k=1,
        embedding_config={
            "provider": "local_minilm",
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "enabled": True,
            "log_file": str(log_file),
        },
    )

    output = capsys.readouterr().out
    assert "[embedding] start provider=local_minilm" in output
    assert "[embedding] vectors encoded count=3 dim=2" in output
    assert "[embedding] retrieval done hits=1" in output
    rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["start", "model_loaded", "vectors_encoded", "retrieval_done"]
    assert rows[0]["record_count"] == 2
    assert rows[2]["vector_count"] == 3
    assert rows[2]["vector_dim"] == 2
    assert rows[3]["top_hits"][0]["paper_id"] == hits[0].paper_id
