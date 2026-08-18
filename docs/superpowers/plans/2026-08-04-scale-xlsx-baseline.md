# Scale XLSX Baseline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract canonical questionnaire scores from per-subject XLSX workbooks, select one baseline-like record per subject, and merge those baseline scores with fMRI features without follow-up leakage.

**Architecture:** A focused `scale_workbook` module owns workbook discovery, visit-block parsing, duplicate resolution, and baseline selection. `ScaleFeatureExtractor` orchestrates XLSX extraction while preserving its existing tabular fallback, writes long and baseline CSV artifacts, and registers only the baseline table for multimodal merging. Existing subject normalization in `MultimodalMerger` performs the fMRI-scale join.

**Tech Stack:** Python 3.10+, pandas, openpyxl 3.x, pytest, existing `FeatureTable` and `MultimodalMerger` APIs.

## Global Constraints

- Input layout is `sub-*/scales/*_scales.xlsx`.
- Canonical visits are exactly `0w`, `2w`, `3w`, and `6w`.
- Canonical score columns are exactly `ISI`, `PSQI`, `BAI`, `BDI`, and `sleepiness`.
- Baseline selection order is `0w`, `2w`, `3w`, then `6w`.
- A non-`0w` baseline must set `baseline_is_substituted=True` and retain `baseline_source_visit`.
- Follow-up scores must never be averaged into cross-sectional baseline features.
- Treatment effects, change scores, response labels, and healthy-label reclassification are out of scope.

---

### Task 1: Parse Visit-Structured Scale Workbooks

**Files:**
- Create: `sleep_ai_scientist/feature_extraction/extractors/scale_workbook.py`
- Create: `tests/test_scale_workbook.py`

**Interfaces:**
- Produces: `extract_scale_workbooks(root: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]`
- Produces: `select_baseline_scale_rows(long_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]`
- Long columns: `subject_id`, `subject`, `visit`, `ISI`, `PSQI`, `BAI`, `BDI`, `sleepiness`, `source_file`
- Baseline columns: `subject_id`, `subject`, `ISI`, `PSQI`, `BAI`, `BDI`, `sleepiness`, `baseline_source_visit`, `baseline_is_substituted`

- [ ] **Step 1: Write failing parser tests**

Create temporary workbooks with `openpyxl.Workbook`, including repeated headers such as `id基线（0w）`, `id治疗后评估（2w）`, Chinese `嗜睡`, missing score cells, and a corrupt `.xlsx`. Assert canonical long rows, path-derived subject IDs, missing-value preservation, and skipped-file audit metadata.

```python
long_frame, audit = extract_scale_workbooks(tmp_path)
row = long_frame.query("subject_id == 'sub-ISM035' and visit == '0w'").iloc[0]
assert row["ISI"] == 18
assert row["sleepiness"] == 1
assert row["source_file"].endswith("sub-ISM035_scales.xlsx")
assert audit["skipped_file_count"] == 1
```

- [ ] **Step 2: Run parser tests and verify RED**

Run: `python -m pytest tests/test_scale_workbook.py -q`

Expected: collection fails with `ModuleNotFoundError` for `scale_workbook`.

- [ ] **Step 3: Implement workbook discovery and parsing**

Use `openpyxl.load_workbook(path, read_only=True, data_only=True)`. Discover sorted `*_scales.xlsx` files below `input_root`, derive `sub-*` from path components, detect visit tokens with `r"(?<!\\d)(0|2|3|6)\\s*w"`, map `嗜睡` to `sleepiness`, and convert only canonical score cells with `pd.to_numeric(errors="coerce")`.

For duplicate `subject_id x visit` rows, preserve the first non-missing value per score, retain the first source path, and increment `duplicate_subject_visit_count`. Catch workbook-level exceptions, append `{path, error}` to `skipped_files`, and continue.

- [ ] **Step 4: Run parser tests and verify GREEN**

Run: `python -m pytest tests/test_scale_workbook.py -q`

Expected: parser tests pass.

- [ ] **Step 5: Write failing baseline-selection tests**

Assert that `0w` wins when present, otherwise `2w` wins over `3w` and `6w`, `3w` wins over `6w`, provenance fields are correct, and subjects with no canonical visit are absent.

```python
baseline, audit = select_baseline_scale_rows(long_frame)
substituted = baseline.set_index("subject_id").loc["sub-NOBASE"]
assert substituted["baseline_source_visit"] == "2w"
assert bool(substituted["baseline_is_substituted"]) is True
assert audit["substituted_baseline_count"] == 1
```

- [ ] **Step 6: Run baseline tests and verify RED**

Run: `python -m pytest tests/test_scale_workbook.py -q`

Expected: failure because `select_baseline_scale_rows` is missing or does not implement visit priority.

- [ ] **Step 7: Implement baseline selection**

Validate required identity/visit columns, rank visits with `{"0w": 0, "2w": 1, "3w": 2, "6w": 3}`, sort stably by subject and rank, select one row per subject, rename `visit` to `baseline_source_visit`, add the substitution boolean, and return selection audit counts.

- [ ] **Step 8: Run all workbook tests**

Run: `python -m pytest tests/test_scale_workbook.py -q`

Expected: all workbook parsing and baseline tests pass.

---

### Task 2: Integrate XLSX Artifacts Into ScaleFeatureExtractor

**Files:**
- Modify: `sleep_ai_scientist/feature_extraction/extractors/scale_feature_extractor.py`
- Create: `tests/test_scale_feature_extractor.py`

**Interfaces:**
- Consumes: `extract_scale_workbooks(...)` and `select_baseline_scale_rows(...)` from Task 1.
- Produces: existing `ScaleFeatureExtractor.run(*, plan_id: str, output_dir: str | Path) -> FeatureTable | None`.
- Produces artifacts: `scale_features_long.csv` and `scale_features.csv`.
- `FeatureTable.path` must point to baseline `scale_features.csv`; `FeatureTable.metadata["long_table"]` must point to `scale_features_long.csv`.

- [ ] **Step 1: Write failing extractor tests**

Build two valid workbooks, one with true `0w` and one with only `2w/6w`. Run the real extractor and assert both CSVs exist, only the baseline CSV is registered, follow-up values are absent from baseline scores, and audit counts appear in metadata. Add a test that an existing `features_csv` still uses the legacy tabular path.

```python
table = ScaleFeatureExtractor({"input_root": str(tmp_path)}).run(
    plan_id="plan_scale", output_dir=tmp_path / "out"
)
baseline = pd.read_csv(table.path).set_index("subject_id")
assert baseline.loc["sub-ISM035", "baseline_source_visit"] == "0w"
assert baseline.loc["sub-NOBASE", "baseline_source_visit"] == "2w"
assert Path(table.metadata["long_table"]).name == "scale_features_long.csv"
```

- [ ] **Step 2: Run extractor tests and verify RED**

Run: `python -m pytest tests/test_scale_feature_extractor.py -q`

Expected: failure because the existing extractor does not read XLSX or write a long table.

- [ ] **Step 3: Implement XLSX orchestration with tabular fallback**

When `input_root` or `raw_root` contains at least one `*_scales.xlsx`, call the Task 1 APIs, write long and baseline CSVs, and return a baseline `FeatureTable` with extraction/audit metadata. When no XLSX exists, retain the existing `extract_tabular_features` behavior unchanged. Return `None` only when neither source yields rows.

- [ ] **Step 4: Run extractor tests and verify GREEN**

Run: `python -m pytest tests/test_scale_feature_extractor.py -q`

Expected: all extractor tests pass.

---

### Task 3: Verify fMRI-Scale Merge And Enable Default Discovery Input

**Files:**
- Modify: `configs/experiment_config.yaml`
- Modify: `pyproject.toml`
- Modify: `environment.yml`
- Create: `tests/test_scale_multimodal_merge.py`
- Create: `tests/test_scale_configuration.py`

**Interfaces:**
- Consumes: baseline `FeatureTable` from Task 2 and existing `MultimodalMerger.run(...)`.
- Produces merged fields: `scales_ISI`, `scales_PSQI`, `scales_BAI`, `scales_BDI`, `scales_sleepiness`, `scales_baseline_source_visit`, and `scales_baseline_is_substituted`.

- [ ] **Step 1: Write a merge contract test and a failing configuration test**

Create an fMRI `FeatureTable` with repeated scan rows for one subject and a baseline scale `FeatureTable` with one row per subject. Assert one merged row per subject, numeric fMRI aggregation, preserved scale provenance, and baseline values rather than follow-up values.

```python
merged_path = MultimodalMerger().run([fmri_table, scale_table], tmp_path / "merged.csv")
merged = pd.read_csv(merged_path).set_index("subject")
assert merged.loc["sub-ISM035", "fmri_thalamus_DMN_FC"] == pytest.approx(0.3)
assert merged.loc["sub-ISM035", "scales_ISI"] == 18
assert merged.loc["sub-ISM035", "scales_baseline_source_visit"] == "0w"
```

Load `configs/experiment_config.yaml`, `pyproject.toml`, and `environment.yml`.
Assert that the sourcedata root is configured for scales and that both package
manifests declare `openpyxl>=3.1`.

- [ ] **Step 2: Run configuration test and verify RED**

Run: `python -m pytest tests/test_scale_configuration.py -q`

Expected: failure because the scales input root and `openpyxl` dependency are not declared.

- [ ] **Step 3: Make the minimal integration/configuration changes**

Set `feature_extraction.scales.input_root` to `/data/fmri_agent/multimodal_sleep_data/bids/sourcedata`. Add `openpyxl>=3.1` to `pyproject.toml` runtime dependencies and `environment.yml` pip dependencies.

Run the merge contract test before changing `MultimodalMerger`. If it passes,
leave the merger unchanged. If it fails, add a focused failing assertion for
the observed contract defect before applying the minimal merger fix.

- [ ] **Step 4: Run focused feature tests**

Run: `python -m pytest tests/test_scale_workbook.py tests/test_scale_feature_extractor.py tests/test_scale_multimodal_merge.py tests/test_scale_configuration.py tests/test_grounding_validation.py tests/test_script_smoke.py -q`

Expected: all selected tests pass without warnings caused by the new code.

- [ ] **Step 5: Run against real sourcedata**

Invoke `ScaleFeatureExtractor` with the real sourcedata root and a temporary output directory. Merge its returned baseline table with `data/foundation/multimodal_master_table.csv` through a temporary fMRI `FeatureTable`. Report discovered/parsed/skipped workbook counts, visit distribution, baseline substitutions, scale subjects, and subject overlap in the merged output.

- [ ] **Step 6: Verify repository diff and output contract**

Run: `git diff --check` and inspect `git diff -- sleep_ai_scientist/feature_extraction configs/experiment_config.yaml pyproject.toml environment.yml tests/test_scale_workbook.py tests/test_scale_feature_extractor.py tests/test_scale_multimodal_merge.py`.

Expected: no whitespace errors; only planned files changed; no treatment-effect code or healthy-label changes.
