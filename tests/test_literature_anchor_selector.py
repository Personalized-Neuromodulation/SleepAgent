from sleep_ai_scientist.literature.anchor_selector import select_anchor_papers
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_anchor_selector_not_only_insomnia():
    records = [
        LiteratureRecord(paper_id="i1", title="Insomnia EEG slow wave", abstract="insomnia EEG"),
        LiteratureRecord(paper_id="a1", title="Mouse orexin optogenetic sleep", abstract="mice orexin optogenetic"),
    ]
    anchors = select_anchor_papers(records, ["insomnia_clinical_application", "animal_causal_sleep"], per_group=1)
    ids = {item["paper_id"] for item in anchors}
    assert "i1" in ids
    assert "a1" in ids

