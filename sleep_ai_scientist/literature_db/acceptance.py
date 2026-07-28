from __future__ import annotations

from sqlalchemy import func, select

from .engine import create_database_engine, session_scope
from .models import AbstractVersion, DedupDecision, Paper, PaperIdentifier
from .repository import LiteratureRepository
from .schemas import (
    AbstractVersionCreate,
    CandidateCreate,
    DedupDecisionCreate,
    IdentifierCreate,
    PaperAuthorCreate,
    PaperCreate,
    PaperSourceCreate,
    UpdateRunCreate,
)


def run_metadata_acceptance(config_path: str) -> dict:
    """Run the deterministic two-provider metadata acceptance scenario."""
    engine = create_database_engine(config_path)
    try:
        with session_scope(engine) as session:
            repository = LiteratureRepository()
            run = repository.create_update_run(
                session, UpdateRunCreate(run_type="schema_test", status="running")
            )
            candidate_a_input = CandidateCreate(
                source_name="pubmed",
                source_record_id="pmid-test-001",
                discovery_method="api_search",
                discovery_query="fixed local acceptance fixture",
                raw_title="Sleep Restriction and Functional Connectivity",
                raw_abstract="Background: Sleep restriction alters functional connectivity.",
                raw_doi="https://doi.org/10.1234/sleepagent.test.001",
                raw_pmid="PMID: 90000001",
                raw_journal="Journal of Sleep Metadata",
                raw_publication_date="2025-01-15",
                raw_authors=[
                    {"given_name": "Ada", "family_name": "Liu"},
                    {"given_name": "Noah", "family_name": "Smith"},
                ],
                raw_payload={"provider": "pubmed", "fixture": "A"},
            )
            candidate_a = repository.create_candidate(
                session, candidate_a_input, run=run
            )
            paper = repository.create_canonical_paper(
                session,
                PaperCreate(
                    canonical_title="Sleep Restriction and Functional Connectivity",
                    journal_name="Journal of Sleep Metadata",
                    publication_date="2025-01-15",
                    first_author="Ada Liu",
                ),
            )
            stable_paper_id = paper.paper_id
            repository.add_identifier(
                session,
                paper,
                IdentifierCreate(
                    identifier_type="doi",
                    raw_value=candidate_a_input.raw_doi or "",
                    source_name="pubmed",
                    is_primary=True,
                ),
            )
            repository.add_identifier(
                session,
                paper,
                IdentifierCreate(
                    identifier_type="pmid",
                    raw_value=candidate_a_input.raw_pmid or "",
                    source_name="pubmed",
                    is_primary=True,
                ),
            )
            repository.replace_paper_authors(
                session,
                paper,
                [
                    PaperAuthorCreate(
                        author_order=1,
                        given_name="Ada",
                        family_name="Liu",
                        source_name="pubmed",
                    ),
                    PaperAuthorCreate(
                        author_order=2,
                        given_name="Noah",
                        family_name="Smith",
                        source_name="pubmed",
                    ),
                ],
            )
            repository.add_paper_source(
                session,
                paper,
                candidate_a,
                PaperSourceCreate(
                    source_name="pubmed",
                    source_record_id="pmid-test-001",
                    discovery_method="api_search",
                    match_method="create_new",
                    match_score=1.0,
                ),
            )
            abstract_a = repository.add_abstract_version(
                session,
                paper,
                AbstractVersionCreate(
                    source_name="pubmed",
                    abstract_text=candidate_a_input.raw_abstract or "",
                    quality_score=0.9,
                ),
            )
            repository.set_preferred_abstract(session, paper, abstract_a)
            repository.record_dedup_decision(
                session,
                candidate_a,
                DedupDecisionCreate(
                    decision="create_new", match_method="no_existing_identifier"
                ),
                matched_paper=paper,
            )

            candidate_b_input = CandidateCreate(
                source_name="europe_pmc",
                source_record_id="epmc-test-001",
                discovery_method="api_search",
                raw_title="Sleep restriction alters brain functional connectivity",
                raw_abstract="Sleep restriction was associated with altered connectivity in a local fixture.",
                raw_doi="doi:10.1234/SLEEPAGENT.TEST.001",
                raw_journal="Journal of Sleep Metadata",
                raw_publication_date="2025-01",
                raw_payload={"provider": "europe_pmc", "fixture": "B"},
            )
            candidate_b = repository.create_candidate(
                session, candidate_b_input, run=run
            )
            matched = repository.find_paper_by_identifier(
                session, "doi", candidate_b_input.raw_doi or ""
            )
            if matched is None:
                raise AssertionError("Candidate B DOI did not resolve to Candidate A paper")
            repository.add_identifier(
                session,
                matched,
                IdentifierCreate(
                    identifier_type="doi",
                    raw_value=candidate_b_input.raw_doi or "",
                    source_name="europe_pmc",
                ),
            )
            repository.add_paper_source(
                session,
                matched,
                candidate_b,
                PaperSourceCreate(
                    source_name="europe_pmc",
                    source_record_id="epmc-test-001",
                    discovery_method="api_search",
                    match_method="doi",
                    match_score=1.0,
                ),
            )
            repository.add_abstract_version(
                session,
                matched,
                AbstractVersionCreate(
                    source_name="europe_pmc",
                    abstract_text=candidate_b_input.raw_abstract or "",
                    quality_score=0.8,
                ),
            )
            repository.record_dedup_decision(
                session,
                candidate_b,
                DedupDecisionCreate(
                    decision="exact_match", match_method="doi", match_score=1.0
                ),
                matched_paper=matched,
            )
            first_counts = repository.row_counts(session)

            # Repeat all idempotent inputs in the same run.
            candidate_a_again = repository.create_candidate(
                session, candidate_a_input, run=run
            )
            candidate_b_again = repository.create_candidate(
                session, candidate_b_input, run=run
            )
            repository.add_identifier(
                session,
                paper,
                IdentifierCreate(
                    identifier_type="doi", raw_value=candidate_a_input.raw_doi or ""
                ),
            )
            repository.add_paper_source(
                session,
                paper,
                candidate_a_again,
                PaperSourceCreate(
                    source_name="pubmed",
                    source_record_id="pmid-test-001",
                    discovery_method="api_search",
                    match_method="create_new",
                    match_score=1.0,
                ),
            )
            repository.add_paper_source(
                session,
                paper,
                candidate_b_again,
                PaperSourceCreate(
                    source_name="europe_pmc",
                    source_record_id="epmc-test-001",
                    discovery_method="api_search",
                    match_method="doi",
                    match_score=1.0,
                ),
            )
            repository.add_abstract_version(
                session,
                paper,
                AbstractVersionCreate(
                    source_name="pubmed",
                    abstract_text=candidate_a_input.raw_abstract or "",
                    quality_score=0.9,
                ),
            )
            repository.add_abstract_version(
                session,
                paper,
                AbstractVersionCreate(
                    source_name="europe_pmc",
                    abstract_text=candidate_b_input.raw_abstract or "",
                    quality_score=0.8,
                ),
            )
            final_counts = repository.row_counts(session)
            current_decisions = session.scalar(
                select(func.count())
                .select_from(DedupDecision)
                .where(DedupDecision.is_current.is_(True))
            )
            preferred_abstracts = session.scalar(
                select(func.count())
                .select_from(AbstractVersion)
                .where(AbstractVersion.is_preferred.is_(True))
            )
            doi_count = session.scalar(
                select(func.count())
                .select_from(PaperIdentifier)
                .where(PaperIdentifier.identifier_type == "doi")
            )
            paper_count = session.scalar(select(func.count()).select_from(Paper))
            repository.complete_update_run(
                session, run, counts=final_counts, status="completed"
            )

            expected = {
                "literature_update_runs": 1,
                "literature_candidates": 2,
                "literature_papers": 1,
                "literature_paper_authors": 2,
                "literature_paper_identifiers": 2,
                "literature_paper_sources": 2,
                "literature_abstract_versions": 2,
            }
            counts_match = all(final_counts[key] == value for key, value in expected.items())
            idempotent_keys = (
                "literature_candidates",
                "literature_papers",
                "literature_paper_identifiers",
                "literature_paper_sources",
                "literature_abstract_versions",
            )
            idempotent = all(first_counts[key] == final_counts[key] for key in idempotent_keys)
            success = all(
                (
                    counts_match,
                    idempotent,
                    matched.paper_id == stable_paper_id,
                    candidate_a.linked_paper_id == candidate_b.linked_paper_id,
                    current_decisions == 2,
                    preferred_abstracts == 1,
                    doi_count == 1,
                    paper_count == 1,
                )
            )
            return {
                "success": success,
                "paper_id": str(stable_paper_id),
                "candidate_a_id": str(candidate_a.candidate_id),
                "candidate_b_id": str(candidate_b.candidate_id),
                "candidates_share_paper_id": candidate_a.linked_paper_id
                == candidate_b.linked_paper_id,
                "doi_deduplicated": doi_count == 1,
                "current_dedup_decisions": current_decisions,
                "preferred_abstracts": preferred_abstracts,
                "first_counts": first_counts,
                "final_counts": final_counts,
                "idempotent_rerun": idempotent,
            }
    finally:
        engine.dispose()
