# YangZhi Healthy-Control Scale Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely import 22 healthy-control baseline scale rows into their exact `sub-YZHC*` sourcedata workbooks.

**Architecture:** A dedicated importer parses and validates the source workbook, stages modified target workbooks and manifests, backs up current placeholders, and atomically installs the staged files. Existing scale extraction remains responsible for downstream long/baseline tables.

**Tech Stack:** Python 3.10+, openpyxl, pathlib, json, shutil, tempfile, pytest.

## Global Constraints

- Accept source IDs only with `^YZ_HC_(\d{3})$`.
- Use exact target IDs `sub-YZHC<digits>`.
- Copy scores by header name and never copy the name column.
- Fill only `0w`; preserve all later visit rows.
- Validate all 22 mappings before writing any target.
- Backup and stage before atomic replacement.

---

### Task 1: Parse And Validate Healthy-Control Source Rows

**Files:**
- Create: `sleep_ai_scientist/feature_extraction/yangzhi_hc_scale_import.py`
- Create: `tests/test_yangzhi_hc_scale_import.py`

**Interfaces:**
- Produce: `parse_yangzhi_hc_source(path: str | Path) -> list[dict[str, Any]]`
- Each record contains `source_id`, `subject_id`, and score fields from `睡眠效率` through `BDI`.

- [ ] Write tests proving exact `YZ_HC_020 -> sub-YZHC020` mapping and rejection of `YZ_ISM_020`.
- [ ] Run `python -m pytest tests/test_yangzhi_hc_scale_import.py -q` and verify RED.
- [ ] Implement exact header/ID parsing with duplicate and required-column validation.
- [ ] Re-run the focused tests and verify GREEN.

### Task 2: Stage, Backup, And Install Baseline Rows

**Files:**
- Modify: `sleep_ai_scientist/feature_extraction/yangzhi_hc_scale_import.py`
- Modify: `tests/test_yangzhi_hc_scale_import.py`

**Interfaces:**
- Produce: `import_yangzhi_hc_scales(source_excel, sourcedata_root, backup_dir, *, apply=False) -> dict[str, Any]`
- CLI: `python -m sleep_ai_scientist.feature_extraction.yangzhi_hc_scale_import --source ... --sourcedata-root ... --backup-dir ... --apply`

- [ ] Write tests for dry-run validation, canonical A-cell identity, score copying, name exclusion, later-row preservation, backup files, and manifest status.
- [ ] Run focused tests and verify RED.
- [ ] Implement staging, complete preflight validation, backup, atomic replacement, rollback, report writing, and CLI argument parsing.
- [ ] Run focused tests and verify GREEN.

### Task 3: Apply To Real Sourcedata And Verify

**Files:**
- Write externally: `/data/fmri_agent/multimodal_sleep_data/bids/sourcedata/sub-YZHC*/scales/*.xlsx`
- Write externally: corresponding `scale_manifest.json` files and one import report/backup directory.

- [ ] Run dry-run against the real source and assert 22 source rows and 22 targets.
- [ ] Run focused and full repository tests.
- [ ] Request external-write approval and run the importer with `--apply`.
- [ ] Re-run `ScaleFeatureExtractor`, assert 22 `sub-YZHC*` baselines, and regenerate the fMRI-scale merged output.
- [ ] Inspect `sub-YZHC020` values against source row `YZ_HC_020` and verify no names were written.
