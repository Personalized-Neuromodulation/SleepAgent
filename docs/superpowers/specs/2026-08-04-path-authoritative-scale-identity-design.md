# Path-Authoritative Scale Identity Design

## Goal

Prevent questionnaire records from being assigned to subjects by shared
numeric suffixes or workbook-internal identifiers. The `sub-*` directory that
contains a `scales` workbook is the only subject identity used by downstream
tables and multimodal merges.

## Identity Contract

The supported directory namespaces are `sub-ISM*`, `sub-YZ*`, and
`sub-YZHC*`. The exact nearest `sub-*` path component is copied without
rewriting into both `subject_id` and `subject`.

For example:

```text
sourcedata/sub-YZ020/scales/sub-YZ020_scales.xlsx
workbook row ID: YZ_ISM_020
downstream subject_id: sub-YZ020
downstream subject: sub-YZ020
```

The workbook row ID is not normalized, compared by suffix, or used as a merge
key. In particular, `YZ_ISM_020`, `sub-YZ020`, and `sub-YZHC020` are not
interchangeable identifiers.

If two workbooks in different `sub-*` directories contain the same internal
row ID, each record remains assigned to its own directory subject. No
deduplication or reassignment occurs across directory subjects.

## Audit Contract

The long and baseline feature tables contain canonical directory identities
only. Workbook-internal IDs are retained only in extraction audit metadata so
they cannot accidentally become downstream join keys.

The audit metadata records:

- `subject_assignment_policy: path_authoritative`
- observed workbook row IDs grouped by directory subject;
- count and details of rows whose internal ID text differs from the directory
  subject ID;
- files with visit headers but no usable score rows as
  `no_usable_scale_scores`;
- skipped or unreadable files separately from readable no-score files.

An internal-ID difference is informational. It does not skip, rename, or
reassign a record.

## Data Flow

`ScaleFeatureExtractor` discovers each `*_scales.xlsx` under a `sub-*/scales`
directory. `scale_workbook` obtains the subject identity from the path before
reading workbook cells. Every parsed visit row receives that directory ID.

`scale_features_long.csv`, `scale_features.csv`, and the multimodal merged
table therefore use only canonical directory IDs. Existing visit selection
continues to prefer `0w`, then `2w`, `3w`, and `6w`.

## Validation And Testing

Tests will verify that:

- a workbook row ID `YZ_ISM_020` under `sub-YZ020/scales` outputs
  `subject_id=sub-YZ020`;
- numeric suffixes are never sufficient to assign or merge a subject;
- the same internal ID under `sub-YZ020` and `sub-YZHC020` produces two
  distinct directory subjects;
- no internal workbook ID appears in downstream identity columns;
- audit metadata declares `path_authoritative` and records internal-ID
  differences;
- readable header-only workbooks remain classified as having no usable scale
  scores.

The real sourcedata tree will be reprocessed after tests pass. Verification
will inspect identity namespaces, duplicate subjects, audit counts, and the
fMRI-scale merge keys.

## Out Of Scope

- Renaming existing `sub-*` directories.
- Inferring clinical identity from numeric suffixes.
- Creating a clinical subject crosswalk.
- Reassigning a workbook to a different directory subject.
- Filling missing scale scores from another subject or cohort.
