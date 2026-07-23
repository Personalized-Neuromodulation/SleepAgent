# Experiment-Driven Literature Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace repeated fixed-query literature refreshes in discovery iterations with experiment-driven query expansion that appends accepted new queries before refreshing literature.

**Architecture:** Add a focused literature expansion module that reads experiment summaries/results, optional LLM suggestions, and existing query YAML to produce an expansion plan. Discovery loop updates foundation every eligible iteration, builds the expansion plan, refreshes literature only when accepted new queries exist, and always refreshes grounding when foundation changed.

**Tech Stack:** Python 3.12, pytest, existing YAML/JSON helpers, existing LLM client patterns, existing literature builder.

## Global Constraints

- Fixed bootstrap queries remain in `configs/literature_queries.yaml`; later iterations must not rerun fixed queries unless new accepted queries are appended.
- New queries must be derived from experiment results via LLM-assisted intent parsing plus deterministic validation.
- New accepted queries must be appended to the original query list under an experiment feedback expansion group.
- Logs must show extracted signals, candidate count, accepted/rejected counts, appended query count, and literature refresh skip/run reason.
- Keep implementation deterministic when LLM is unavailable by using rule-generated fallback candidates.

---

### Task 1: Query Expansion Planner

**Files:**
- Create: `sleep_ai_scientist/literature/experiment_intent.py`
- Test: `tests/test_experiment_literature_intent.py`

**Interfaces:**
- Produces: `build_literature_expansion_plan(experiment_summary: dict[str, Any], iteration_id: str, query_config_path: str | Path, *, llm_client: Any | None = None, llm_config: dict[str, Any] | None = None, max_queries: int = 8) -> dict[str, Any]`
- Produces: `append_queries_to_config(query_config_path: str | Path, accepted_queries: list[dict[str, Any]], *, group: str = "experiment_feedback_expansion") -> dict[str, Any]`

- [ ] **Step 1: Write failing tests**

Create tests that:
- build an experiment summary with a failed primary test, failed negative control, missing variables, and modality gap;
- assert accepted queries are generated, deduplicated against existing YAML, and include provenance;
- assert appending writes accepted queries under `experiment_feedback_expansion`.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_experiment_literature_intent.py -v`
Expected: FAIL because module/functions do not exist.

- [ ] **Step 3: Implement minimal planner**

Implement:
- structured signal extraction from `experiment_summary`;
- rule fallback candidates for failed tests, negative controls, missing variables, modality gaps, and validated pathways;
- optional strict JSON LLM candidate ingestion;
- deterministic query normalization, validation, de-duplication, priority sorting, and max query limiting;
- YAML appending while preserving existing query groups.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_experiment_literature_intent.py -v`
Expected: PASS.

### Task 2: Discovery Loop Integration

**Files:**
- Modify: `sleep_ai_scientist/discovery_loop/discovery_runner.py`
- Test: `tests/test_discovery_loop.py`

**Interfaces:**
- Consumes: `build_literature_expansion_plan(...)`
- Consumes: `append_queries_to_config(...)`
- Changes: `_refresh_literature_if_needed(...)` should depend on accepted query count, not `foundation_changed` alone.

- [ ] **Step 1: Write failing tests**

Add/adjust tests that:
- verify literature refresh is skipped when foundation changed but no accepted queries exist;
- verify accepted queries are appended and literature refresh is called when expansion plan has new queries;
- verify grounding refresh still runs when foundation changed even if literature refresh is skipped.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_discovery_loop.py -v`
Expected: FAIL on old fixed-query refresh behavior.

- [ ] **Step 3: Implement discovery integration**

Update loop order:
`foundation_update -> literature_expansion_plan -> append accepted queries -> conditional literature refresh -> grounding refresh`.

Add log lines:
- `[literature_intent] start ...`
- `[literature_intent] extracted signals ...`
- `[literature_intent] candidates generated=...`
- `[literature_intent] accepted=... rejected_duplicate=... rejected_invalid=...`
- `[literature_intent] appended query_config=... group=... count=...`
- `[literature_refresh] skipped reason=no_new_experiment_queries`
- `[literature_refresh] incremental start new_queries=...`

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_discovery_loop.py tests/test_experiment_literature_intent.py -v`
Expected: PASS.

### Task 3: Focused Regression Suite

**Files:**
- Modify as needed: `tests/test_hypothesis_experiment_script_logging.py`
- Run existing targeted tests.

**Interfaces:**
- Ensures shell/test assumptions still match discovery loop behavior.

- [ ] **Step 1: Run focused suite**

Run: `pytest tests/test_discovery_loop.py tests/test_experiment_literature_intent.py tests/test_hypothesis_experiment_script_logging.py -v`
Expected: PASS.

- [ ] **Step 2: Run broader relevant tests**

Run: `pytest tests/test_literature_db_generation.py tests/test_knowledge_source_generation.py tests/test_knowledge_sources_db_integration.py -v`
Expected: PASS.

## Self-Review

- Spec coverage: plan covers LLM/rule intent parsing, query append, conditional refresh, logs, and grounding continuation.
- Placeholder scan: no placeholders remain.
- Type consistency: planner functions and discovery loop consumers use `dict[str, Any]` and existing path conventions.
