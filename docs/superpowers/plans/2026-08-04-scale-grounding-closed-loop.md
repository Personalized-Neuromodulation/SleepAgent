# Scale Grounding Closed-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize all scale XLSX workbooks into longitudinal and baseline tables, merge baseline scales with fMRI FC, and validate locked grounding-derived FC specs on healthy versus non-healthy subjects.

**Architecture:** Existing `scale_workbook.py` owns workbook parsing and baseline selection. Existing `ScaleFeatureExtractor` writes `scale_features_long.csv` and `scale_features.csv`. Existing grounding validation will be extended to retain baseline clinical anchors and a new compiler will turn ranked grounding hypotheses into locked validation specs.

**Tech Stack:** Python 3.10+, pandas, openpyxl, scipy, scikit-learn, pytest.

## Global Constraints

- Subject identity must come from the `sub-*` path directory.
- Supported visits are exactly `0w`, `2w`, `3w`, and `6w`.
- Standard score fields are exactly `ISI`, `PSQI`, `BAI`, `BDI`, and `sleepiness`.
- Baseline uses `0w`; when missing, substitute by priority `2w`, `3w`, then `6w`.
- Treatment-response statistical modeling is out of scope.
- Healthy subjects are identified by the `sub-YZHC` prefix.
- Validation specs must have `source = "grounding"`.
- Local data must not choose `candidate_fc`; validation uses only the locked spec list.

---

### Task 1: Verify Longitudinal Scale Standardization On Realistic Workbooks

**Files:**
- Modify: `tests/test_scale_workbook.py`
- Modify: `sleep_ai_scientist/feature_extraction/extractors/scale_workbook.py`

**Interfaces:**
- Consumes: `extract_scale_workbooks(root: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]`
- Produces: a long table with supported visits only and canonical score columns.

- [ ] Add a failing test where one subject has `0w`, `2w`, `3w`, `6w`, and unsupported `10w`; assert only the four supported visits appear.
- [ ] Run `python -m pytest tests/test_scale_workbook.py -q` and verify the new test fails if current behavior is incomplete.
- [ ] Update parsing only if the test exposes a gap.
- [ ] Re-run `python -m pytest tests/test_scale_workbook.py -q` and verify it passes.

### Task 2: Verify Scale Feature Artifacts And fMRI Merge

**Files:**
- Modify: `tests/test_scale_feature_extractor.py`
- Modify: `tests/test_scale_multimodal_merge.py`
- Modify: `sleep_ai_scientist/feature_extraction/extractors/scale_feature_extractor.py`
- Modify: `sleep_ai_scientist/feature_extraction/extractors/multimodal_merger.py`

**Interfaces:**
- Consumes: `ScaleFeatureExtractor.run(plan_id: str, output_dir: str | Path)`
- Consumes: `MultimodalMerger().run(tables, output_path)`
- Produces: `scale_features_long.csv`, `scale_features.csv`, and a merged fMRI-scale table.

- [ ] Add a failing test asserting `scale_features_long.csv` contains visit rows while `scale_features.csv` contains one baseline row per subject.
- [ ] Add a failing test asserting baseline scale columns attach to repeated fMRI rows by subject.
- [ ] Run focused tests and verify RED if any required behavior is missing.
- [ ] Update extractor or merger only for missing behavior.
- [ ] Re-run focused tests and verify GREEN.

### Task 3: Compile Ranked Grounding Hypothesis Into Locked Validation Spec

**Files:**
- Create: `sleep_ai_scientist/hypothesis/validation_spec.py`
- Create: `tests/test_validation_spec.py`

**Interfaces:**
- Produces: `compile_grounding_validation_spec(hypothesis: dict[str, Any], *, selected_rank: int | None = None) -> dict[str, Any]`
- The returned spec contains `source`, `hypothesis_id`, `evidence_ids`, `candidate_fc`, `expected_direction`, `clinical_anchors`, and `locked`.

- [ ] Write a failing test that compiles a grounding-ranked hypothesis with evidence IDs, FC candidates, and expected directions.
- [ ] Write a failing test that rejects hypotheses without grounding evidence or without `candidate_fc`.
- [ ] Run `python -m pytest tests/test_validation_spec.py -q` and verify RED.
- [ ] Implement the minimal compiler.
- [ ] Re-run `python -m pytest tests/test_validation_spec.py -q` and verify GREEN.

### Task 4: Retain Clinical Anchors In Grounding-Locked Validation

**Files:**
- Modify: `tests/test_grounding_validation.py`
- Modify: `sleep_ai_scientist/experiment/grounding_validation.py`

**Interfaces:**
- Consumes: locked spec from Task 3.
- Produces: validation outputs that include candidate FC and available scale anchor columns.

- [ ] Add a failing test where the master table contains `ISI`, `PSQI`, `BAI`, `BDI`, and `sleepiness`; assert subject-level validation output retains those columns.
- [ ] Run `python -m pytest tests/test_grounding_validation.py -q` and verify RED.
- [ ] Extend validation table building to keep available clinical anchor columns for interpretation while classifier features remain `candidate_fc` only.
- [ ] Re-run `python -m pytest tests/test_grounding_validation.py -q` and verify GREEN.

### Task 5: Real Data Smoke Verification

**Files:**
- No required source changes.
- Writes outputs under `outputs/scale_features` and `outputs/health_classification`.

**Interfaces:**
- Consumes real sourcedata root `/data/fmri_agent/multimodal_sleep_data/bids/sourcedata`.
- Consumes `data/foundation/multimodal_master_table.csv`.
- Consumes locked grounding spec.

- [ ] Run `ScaleFeatureExtractor` against the real sourcedata root and write `outputs/scale_features`.
- [ ] Verify healthy controls have non-empty baseline scale rows.
- [ ] Merge baseline scales with the master fMRI table.
- [ ] Run grounding-locked validation on the merged table.
- [ ] Run `python -m pytest tests/test_scale_workbook.py tests/test_scale_feature_extractor.py tests/test_scale_multimodal_merge.py tests/test_validation_spec.py tests/test_grounding_validation.py -q`.
- [ ] Run `git diff --check`.
