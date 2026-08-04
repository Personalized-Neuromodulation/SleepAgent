# Scale XLSX Baseline Integration Design

## Goal

Add reproducible extraction of questionnaire scores from each
`sub-*/scales/*_scales.xlsx` workbook and merge one baseline-like scale record
per subject with fMRI functional-connectivity features.

This phase supports cross-sectional healthy versus non-healthy analysis only.
It does not estimate treatment effects, calculate longitudinal change scores,
or assign treatment-response labels.

## Input Contract

- Root layout: `sub-*/scales/*_scales.xlsx`.
- The subject identifier comes from the nearest `sub-*` path component, not
  from free-form identifiers inside the workbook.
- Workbooks contain repeated header/data blocks for visits such as `0w`, `2w`,
  `3w`, and `6w`.
- The canonical scale columns are:
  - `ISI`
  - `PSQI`
  - `BAI`
  - `BDI`
  - `sleepiness`, mapped from the Chinese label `嗜睡`
- Missing or non-numeric scores are represented as missing values. One missing
  score does not invalidate the other scores for that subject and visit.

## Extraction Design

`ScaleFeatureExtractor` will detect XLSX input under its configured
`input_root` or `raw_root`. A dedicated workbook parser will use `openpyxl` to
read worksheets and identify visit blocks from header cells containing visit
tokens.

Visit labels will be normalized to lowercase canonical values (`0w`, `2w`,
`3w`, `6w`). Rows whose visit cannot be identified will be skipped and
reported in extraction metadata rather than silently assigned to baseline.

The extractor will emit two tables:

1. `scale_features_long.csv`
   - One row per `subject_id x visit`.
   - Columns: `subject_id`, `subject`, `visit`, `ISI`, `PSQI`, `BAI`, `BDI`,
     `sleepiness`, and `source_file`.
   - Preserves all recognized visits for future longitudinal analysis.

2. `scale_features.csv`
   - One row per subject for the current cross-sectional workflow.
   - Uses `0w` when available.
   - If `0w` is absent, uses the chronologically closest available follow-up in
     the order `2w`, `3w`, then `6w`.
   - Adds `baseline_source_visit` and `baseline_is_substituted` so substituted
     records cannot be mistaken for observed baseline records.
   - Subjects with no recognized visit are excluded and reported in metadata.

If duplicate rows exist for the same subject and visit, the extractor will use
the first non-missing value per canonical scale and report the duplicate in
metadata. It will not average duplicate questionnaire records silently.

## Pipeline Integration

The experiment configuration will point `feature_extraction.scales.input_root`
at the sourcedata root. Auto modality detection will then run the scale
extractor alongside fMRI extraction.

Only `scale_features.csv` will be registered as the scale `FeatureTable` and
passed to `MultimodalMerger`. This prevents follow-up rows from being averaged
or duplicated during subject-level merging. The long table remains an
additional extractor artifact.

The multimodal merge will continue to normalize both modality tables to the
base `sub-*` identifier and join by `subject`. The resulting table will contain
fMRI features plus prefixed scale fields such as `scales_ISI` and
`scales_baseline_source_visit`. The merger will preserve these baseline
provenance fields while still preventing duplicate subject rows.

The grounding-locked healthy/non-healthy validator will use the baseline scale
table only. Follow-up records will not enter classification or cross-sectional
group tests in this phase.

## Error Handling And Auditability

- Missing input roots produce no scale table, preserving current optional
  modality behavior.
- Corrupt or unreadable XLSX files are recorded in extraction metadata; other
  workbooks continue processing.
- Missing required score columns are reported per workbook. Available canonical
  scores are still retained.
- The extractor records discovered files, parsed files, skipped files,
  recognized visits, substituted-baseline count, and subjects without a usable
  visit.
- Each long-table row retains its source workbook path in `source_file`.

## Testing

Focused tests will create temporary XLSX fixtures with `openpyxl` and verify:

- repeated visit blocks become canonical long-form rows;
- Chinese `嗜睡` maps to `sleepiness`;
- real `0w` is preferred over every follow-up;
- missing `0w` falls back in `2w`, `3w`, `6w` order;
- substitution provenance fields are correct;
- missing scores remain missing without dropping the record;
- scale baseline features merge with repeated fMRI rows by normalized subject;
- follow-up values never enter the cross-sectional merged feature values;
- unreadable workbooks are reported without stopping valid workbooks.

After focused tests pass, the extractor will run against the real sourcedata
tree. Verification will report workbook count, subject count, visit coverage,
baseline substitutions, output columns, and overlap with fMRI subjects.

## Out Of Scope

- Treatment-effect estimation.
- Change scores between visits.
- Responder/non-responder labels.
- Mixed-effects longitudinal models.
- Reclassification of `sub-ISMHC*` or changes to the existing healthy-prefix
  rule.
