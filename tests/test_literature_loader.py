from sleep_ai_scientist.grounding.literature_loader import load_literature


def test_load_literature_fixture():
    records = load_literature("data/fixtures/toy_seed_papers.csv")
    assert len(records) == 3
    assert records[0].paper_id == "toy001"
    assert "insomnia" in [item.lower() for item in records[0].keywords]
