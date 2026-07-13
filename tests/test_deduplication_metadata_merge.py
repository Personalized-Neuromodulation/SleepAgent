from sqlalchemy import select

from sleep_ai_scientist.literature.identity_resolution import resolve_and_upsert
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.models import Paper


def test_metadata_merge_keeps_best_abstract_and_identifier_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        resolve_and_upsert(
            LiteratureRecord(paper_id="pmid1", title="Circadian rhythm sleep study", pmid="123", provider="pubmed", abstract="PubMed abstract with useful details."),
            session,
            retrieval_channel="api_broad",
        )
        resolve_and_upsert(
            LiteratureRecord(paper_id="crossref1", title="Circadian rhythm sleep study", pmid="PMID:123", provider="crossref", abstract="", citation_count=25),
            session,
            retrieval_channel="journal_targeted",
        )
        resolve_and_upsert(
            LiteratureRecord(paper_id="pmc1", title="Different sleep open access", pmcid="pmc 555", provider="europe_pmc"),
            session,
            retrieval_channel="api_broad",
        )
        resolve_and_upsert(
            LiteratureRecord(paper_id="pmc2", title="Different sleep open access", pmcid="PMC555", provider="pubmed"),
            session,
            retrieval_channel="journal_targeted",
        )

        papers = list(session.scalars(select(Paper).order_by(Paper.paper_id)))
        pmid_paper = next(paper for paper in papers if paper.pmid == "123")
        pmc_papers = [paper for paper in papers if paper.pmcid == "PMC555"]

        assert len(pmid_paper.sources) == 2
        assert pmid_paper.abstract == "PubMed abstract with useful details."
        assert pmid_paper.citation_count == 25
        assert len(pmc_papers) == 1
    engine.dispose()

