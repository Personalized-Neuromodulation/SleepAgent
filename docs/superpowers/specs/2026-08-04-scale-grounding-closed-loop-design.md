# Scale And Grounding Closed-Loop Design

## Goal

Build a controlled analysis flow that first standardizes all per-subject scale
workbooks into reusable longitudinal and baseline feature tables, then connects
the merged fMRI-scale data to grounding-derived, locked validation specs.

## Scope

This implementation includes standardizing and saving scale features, merging
baseline scales with fMRI FC by subject, compiling selected grounding hypotheses
into validation specs, and validating healthy versus non-healthy status using
only prespecified FC candidates. It does not implement treatment-response
statistical models.

## Scale Data Flow

The scale extractor reads every `sub-*/scales/*_scales.xlsx` under the configured
sourcedata root. Subject identity is always taken from the `sub-*` directory in
the path, not from Excel cell contents. Visit blocks are normalized to `0w`,
`2w`, `3w`, and `6w`; unsupported visits remain excluded from analysis tables.

The long output `scale_features_long.csv` has one row per subject and visit with
canonical fields:

- `subject_id`
- `subject`
- `visit`
- `ISI`
- `PSQI`
- `BAI`
- `BDI`
- `sleepiness`
- `source_file`

The baseline output `scale_features.csv` uses `0w` where available. If `0w` is
missing, it substitutes the closest available follow-up by priority `2w`, then
`3w`, then `6w`, and records `baseline_source_visit` plus
`baseline_is_substituted`.

## Merge Data Flow

Baseline scales are merged with fMRI FC at subject level. The fMRI data may have
multiple rows per subject; the merger keeps existing behavior and attaches the
same baseline scale values to all matching subject rows. The longitudinal table
is saved for future follow-up or treatment-response analysis but is not used for
treatment modeling in this scope.

## Grounding Validation Flow

Grounding evidence remains upstream of local validation:

1. Run grounding evidence generation.
2. Run the original hypothesis generation and ranking.
3. Compile the selected hypothesis into a validation spec.
4. Lock the spec with `source = "grounding"`.
5. Record `hypothesis_id`, `evidence_ids`, `candidate_fc`,
   `expected_direction`, and `clinical_anchors`.
6. Load local healthy/non-healthy data only after the spec is locked.
7. Validate only the FC columns listed in `candidate_fc`.

Local healthy/non-healthy labels must not be used to choose `candidate_fc`.

## Validation Outputs

The validation output includes the subject-level validation table, group FC
statistics, optional connection figures, model metrics, and metadata showing the
grounding spec identity and candidate FC list. If baseline scale columns are
available in the merged table, they are retained as clinical anchors for
interpretation and covariate-aware follow-up work.

## Constraints

- Healthy subjects are identified by the `sub-YZHC` prefix.
- Non-healthy subjects are all other `sub-*` subjects.
- Only `source = "grounding"` validation specs are accepted.
- `candidate_fc` must be non-empty and prespecified in the locked spec.
- Treatment-response statistical modeling is out of scope for this iteration.
