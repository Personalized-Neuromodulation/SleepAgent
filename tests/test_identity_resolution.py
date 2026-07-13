from sleep_ai_scientist.literature.identity_resolution import (
    assign_canonical_paper_id,
    compute_title_hash,
    normalize_doi,
    normalize_pmcid,
    normalize_pmid,
    normalize_title,
)
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_identity_normalizers_and_canonical_id():
    assert normalize_doi("https://doi.org/10.1000/ABC.") == "10.1000/abc"
    assert normalize_pmid("PMID: 12345") == "12345"
    assert normalize_pmcid("pmc 987") == "PMC987"
    assert normalize_title("Sleep, Health: A Study!") == "sleep health a study"
    assert compute_title_hash("Sleep Health") == compute_title_hash("sleep-health")

    record = LiteratureRecord(paper_id="tmp", title="A title", doi="DOI:10.1/ABC")
    assert assign_canonical_paper_id(record) == "doi:10.1/abc"

