from sleep_ai_scientist.grounding.literature_loader import load_literature
from sleep_ai_scientist.grounding.retrieval import retrieve, tfidf_retrieve


def test_keyword_retrieval_returns_ranked_hits():
    records = load_literature("data/fixtures/toy_seed_papers.csv")
    hits = retrieve("thalamocortical insomnia", records, top_k=2)
    assert hits
    assert hits[0].paper_id == "toy001"


def test_tfidf_fallback_returns_hits():
    records = load_literature("data/fixtures/toy_seed_papers.csv")
    hits = tfidf_retrieve("white matter integrity", records, top_k=1)
    assert hits[0].paper_id == "toy003"
