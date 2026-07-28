from __future__ import annotations

import os
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sleep_ai_scientist.literature_db.deduplication import IdentifierConflictError
from sleep_ai_scientist.literature_db.engine import init_database, session_scope
from sleep_ai_scientist.literature_db.models import (
    AbstractVersion,
    Base,
    CandidateRecord,
    DedupDecision,
    JournalCrawlRun,
    JournalScraperProfile,
    Paper,
    PaperAuthor,
    PaperIdentifier,
    PaperRelation,
    PaperSource,
)
from sleep_ai_scientist.literature_db.repository import LiteratureRepository
from sleep_ai_scientist.literature_db.schema import EXPECTED_TABLES
from sleep_ai_scientist.literature_db.schemas import (
    AbstractVersionCreate,
    CandidateCreate,
    DedupDecisionCreate,
    IdentifierCreate,
    JournalScanStateCreate,
    JournalScraperProfileCreate,
    PaperAuthorCreate,
    PaperCreate,
    PaperRelationCreate,
    PaperSourceCreate,
    UpdateRunCreate,
)


@pytest.fixture
def postgres_schema():
    url = os.getenv("SLEEPAGENT_DATABASE_URL")
    if not url:
        pytest.fail("SLEEPAGENT_DATABASE_URL is required; PostgreSQL tests never use alternative backends")
    schema = f"sleepagent_test_{uuid.uuid4().hex}"
    admin = create_engine(url, future=True)
    if admin.dialect.name != "postgresql":
        pytest.fail("SLEEPAGENT_DATABASE_URL must use PostgreSQL")
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, future=True, connect_args={"options": f"-csearch_path={schema}"}
    )
    init_database(engine)
    try:
        yield engine, schema
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _paper(repository: LiteratureRepository, session: Session, title: str) -> Paper:
    return repository.create_canonical_paper(
        session, PaperCreate(canonical_title=title)
    )


def _candidate(source: str, record_id: str) -> CandidateCreate:
    return CandidateCreate(
        source_name=source,
        source_record_id=record_id,
        discovery_method="api_search",
        raw_title="Fixed metadata title",
        raw_payload={"source": source, "record_id": record_id},
    )


def test_schema_has_exact_tables_and_postgresql_types(postgres_schema):
    engine, schema = postgres_schema
    inspector = inspect(engine)
    assert set(inspector.get_table_names(schema=schema)) == set(EXPECTED_TABLES)
    assert "papers" not in inspector.get_table_names(schema=schema)
    uuid_columns = {
        "literature_update_runs": "run_id",
        "literature_candidates": "candidate_id",
        "literature_papers": "paper_id",
        "literature_paper_authors": "paper_author_id",
        "literature_paper_identifiers": "identifier_id",
        "literature_paper_sources": "paper_source_id",
        "literature_abstract_versions": "abstract_id",
        "literature_dedup_decisions": "decision_id",
        "literature_paper_relations": "relation_id",
        "literature_journal_urls": "journal_url_id",
        "literature_journal_scraper_profiles": "scraper_profile_id",
        "literature_journal_crawl_runs": "crawl_run_id",
    }
    for table, name in uuid_columns.items():
        columns = {item["name"]: item for item in inspector.get_columns(table, schema=schema)}
        assert isinstance(columns[name]["type"], UUID)
    candidate_columns = {
        item["name"]: item for item in inspector.get_columns("literature_candidates", schema=schema)
    }
    assert isinstance(candidate_columns["raw_payload"]["type"], JSONB)
    assert candidate_columns["created_at"]["type"].timezone is True


def test_key_constraints_indexes_and_foreign_keys(postgres_schema):
    engine, schema = postgres_schema
    inspector = inspect(engine)
    abstract_indexes = {
        item["name"]: item
        for item in inspector.get_indexes("literature_abstract_versions", schema=schema)
    }
    decision_indexes = {
        item["name"]: item
        for item in inspector.get_indexes("literature_dedup_decisions", schema=schema)
    }
    assert "postgresql_where" in abstract_indexes[
        "uq_literature_abstract_versions_preferred"
    ]["dialect_options"]
    assert "postgresql_where" in decision_indexes[
        "uq_literature_dedup_decisions_current"
    ]["dialect_options"]
    author_checks = {
        item["name"] for item in inspector.get_check_constraints("literature_paper_authors", schema=schema)
    }
    assert "ck_literature_paper_authors_order" in author_checks
    author_fks = inspector.get_foreign_keys("literature_paper_authors", schema=schema)
    assert author_fks[0]["options"]["ondelete"] == "CASCADE"


def test_uuid_is_generated_unique_input_rejected_and_stable(postgres_schema):
    engine, _ = postgres_schema
    with session_scope(engine) as session:
        repository = LiteratureRepository()
        first = _paper(repository, session, "Paper A")
        second = _paper(repository, session, "Paper B")
        assert isinstance(first.paper_id, uuid.UUID)
        assert first.paper_id != second.paper_id
        stable_id = first.paper_id
        first.canonical_title = "Updated Paper A"
        session.flush()
        assert first.paper_id == stable_id
        with pytest.raises(ValidationError):
            PaperCreate(canonical_title="Rejected", paper_id=str(uuid.uuid4()))


def test_candidate_idempotency_and_cross_source_linking(postgres_schema):
    engine, _ = postgres_schema
    with session_scope(engine) as session:
        repository = LiteratureRepository()
        a = repository.create_candidate(session, _candidate("pubmed", "1"))
        duplicate = repository.create_candidate(session, _candidate("pubmed", "1"))
        b = repository.create_candidate(session, _candidate("europe_pmc", "1"))
        paper = _paper(repository, session, "Shared Paper")
        for candidate in (a, b):
            repository.add_paper_source(
                session,
                paper,
                candidate,
                PaperSourceCreate(
                    source_name=candidate.source_name,
                    source_record_id=candidate.source_record_id,
                    discovery_method="api_search",
                    match_method="doi",
                ),
            )
        assert a.candidate_id == duplicate.candidate_id
        assert a.candidate_id != b.candidate_id
        assert a.linked_paper_id == b.linked_paper_id == paper.paper_id
        assert session.scalar(select(func.count()).select_from(CandidateRecord)) == 2


@pytest.mark.parametrize("kind,value", [("doi", "10.1234/x"), ("pmid", "123456")])
def test_identifier_conflict_rollback_keeps_session_usable(
    postgres_schema, kind, value
):
    engine, _ = postgres_schema
    with Session(engine) as session:
        repository = LiteratureRepository()
        first = _paper(repository, session, "First")
        second = _paper(repository, session, "Second")
        repository.add_identifier(
            session, first, IdentifierCreate(identifier_type=kind, raw_value=value)
        )
        session.commit()
        with pytest.raises(IdentifierConflictError):
            repository.add_identifier(
                session, second, IdentifierCreate(identifier_type=kind, raw_value=value)
            )
        session.rollback()
        third = _paper(repository, session, "Session Still Works")
        session.commit()
        assert third.paper_id is not None
        assert session.scalar(select(func.count()).select_from(PaperIdentifier)) == 1


def test_author_order_and_cascade(postgres_schema):
    engine, _ = postgres_schema
    with session_scope(engine) as session:
        repository = LiteratureRepository()
        paper = _paper(repository, session, "Authors")
        with pytest.raises(ValueError):
            repository.replace_paper_authors(
                session, paper, [PaperAuthorCreate(author_order=0)]
            )
        with pytest.raises(ValueError):
            repository.replace_paper_authors(
                session,
                paper,
                [PaperAuthorCreate(author_order=1), PaperAuthorCreate(author_order=1)],
            )
        repository.replace_paper_authors(
            session,
            paper,
            [PaperAuthorCreate(author_order=1), PaperAuthorCreate(author_order=2)],
        )
        session.delete(paper)
        session.flush()
        assert session.scalar(select(func.count()).select_from(PaperAuthor)) == 0


def test_abstract_idempotency_and_preferred_switch(postgres_schema):
    engine, _ = postgres_schema
    with session_scope(engine) as session:
        repository = LiteratureRepository()
        paper = _paper(repository, session, "Abstracts")
        first = repository.add_abstract_version(
            session,
            paper,
            AbstractVersionCreate(source_name="pubmed", abstract_text="First version"),
        )
        duplicate = repository.add_abstract_version(
            session,
            paper,
            AbstractVersionCreate(source_name="pubmed", abstract_text="First version"),
        )
        second = repository.add_abstract_version(
            session,
            paper,
            AbstractVersionCreate(source_name="europe_pmc", abstract_text="Second version"),
        )
        repository.set_preferred_abstract(session, paper, first)
        repository.set_preferred_abstract(session, paper, second)
        assert duplicate.abstract_id == first.abstract_id
        assert session.scalar(select(func.count()).select_from(AbstractVersion)) == 2
        assert session.scalar(
            select(func.count())
            .select_from(AbstractVersion)
            .where(AbstractVersion.is_preferred.is_(True))
        ) == 1
        assert second.is_preferred is True


def test_dedup_decision_history_has_one_current(postgres_schema):
    engine, _ = postgres_schema
    with session_scope(engine) as session:
        repository = LiteratureRepository()
        candidate = repository.create_candidate(session, _candidate("pubmed", "decision"))
        repository.record_dedup_decision(
            session,
            candidate,
            DedupDecisionCreate(decision="manual_review", match_method="title"),
        )
        repository.record_dedup_decision(
            session,
            candidate,
            DedupDecisionCreate(decision="rejected", match_method="manual"),
        )
        assert session.scalar(select(func.count()).select_from(DedupDecision)) == 2
        assert session.scalar(
            select(func.count())
            .select_from(DedupDecision)
            .where(DedupDecision.is_current.is_(True))
        ) == 1


def test_paper_relation_rejects_self_and_is_idempotent(postgres_schema):
    engine, _ = postgres_schema
    with session_scope(engine) as session:
        repository = LiteratureRepository()
        first = _paper(repository, session, "Preprint")
        second = _paper(repository, session, "Published")
        relation_data = PaperRelationCreate(relation_type="is_preprint_of")
        with pytest.raises(ValueError):
            repository.add_paper_relation(session, first, first, relation_data)
        relation = repository.add_paper_relation(session, first, second, relation_data)
        duplicate = repository.add_paper_relation(session, first, second, relation_data)
        assert relation.relation_id == duplicate.relation_id
        assert session.scalar(select(func.count()).select_from(PaperRelation)) == 1


def test_database_constraints_reject_invalid_values(postgres_schema):
    engine, _ = postgres_schema
    with Session(engine) as session:
        paper = Paper(
            canonical_title="Invalid year",
            normalized_title="invalid year",
            publication_year=1200,
            metadata_status="canonical",
        )
        session.add(paper)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        valid = Paper(
            canonical_title="Valid",
            normalized_title="valid",
            metadata_status="canonical",
        )
        session.add(valid)
        session.flush()
        author = PaperAuthor(paper_id=valid.paper_id, author_order=0)
        session.add(author)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_session_scope_rolls_back(postgres_schema):
    engine, _ = postgres_schema
    with pytest.raises(RuntimeError):
        with session_scope(engine) as session:
            _paper(LiteratureRepository(), session, "Rollback")
            raise RuntimeError("force rollback")
    with session_scope(engine) as session:
        assert session.scalar(select(func.count()).select_from(Paper)) == 0


def test_every_planned_journal_records_crawl_run_and_failure_isolated(postgres_schema):
    engine, _ = postgres_schema
    with session_scope(engine) as session:
        repository = LiteratureRepository()
        run = repository.create_update_run(
            session, UpdateRunCreate(run_type="target_journal_scan", status="running")
        )
        ids = []
        for key in ("journal:a", "journal:b"):
            repository.upsert_journal_scan_state(
                session,
                JournalScanStateCreate(
                    journal_key=key,
                    title=key,
                    normalized_title=key,
                    identifier_quality="title_only",
                    source_file="fixture.csv",
                    status="pending",
                ),
            )
            profile = repository.upsert_scraper_profile(
                session,
                key,
                JournalScraperProfileCreate(
                    adapter_name="unresolved",
                    enabled=False,
                    verification_status="manual_review",
                ),
            )
            ids.append((key, profile.scraper_profile_id))
        run_id = run.run_id
    with pytest.raises(RuntimeError):
        with session_scope(engine) as session:
            session.add(
                JournalCrawlRun(
                    update_run_id=run_id,
                    journal_key=ids[0][0],
                    scraper_profile_id=ids[0][1],
                    status="running",
                )
            )
            session.flush()
            raise RuntimeError("journal-local failure")
    with session_scope(engine) as session:
        for index, (key, profile_id) in enumerate(ids):
            session.add(
                JournalCrawlRun(
                    update_run_id=run_id,
                    journal_key=key,
                    scraper_profile_id=profile_id,
                    status=(
                        "temporarily_failed"
                        if index == 0
                        else "completed_no_relevant_papers"
                    ),
                )
            )
    with session_scope(engine) as session:
        assert session.scalar(select(func.count()).select_from(JournalCrawlRun)) == 2
