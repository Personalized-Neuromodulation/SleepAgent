# YangZhi Healthy-Control Scale Import Design

## Goal

Import the 22 baseline questionnaire rows from
`/data/fmri_agent/test_data/YangZhiHC/养志健康人量表统计.xlsx` into the existing
`sub-YZHC001` through `sub-YZHC022` scale workbooks under BIDS sourcedata.

## Identity And Field Mapping

Only source IDs matching `^YZ_HC_(\d{3})$` are accepted. The target is exactly
`sub-YZHC<digits>`; generic numeric-suffix matching is forbidden. The target
directory is the downstream identity, so cell A of the written data row uses
that canonical `sub-YZHC*` value.

The source name column is excluded. Source columns from `睡眠效率` through
`BDI` are copied by exact header name into the corresponding target columns.

## Target Workbook Behavior

Each existing target workbook keeps its six visit header blocks. The importer
fills only the data row immediately following the `0w` header. Existing
`2w/3w/6w/10w/14w` rows remain unchanged and empty. A target is written only
after all 22 source rows, target directories, headers, and one-to-one mappings
validate successfully.

Before replacement, all 22 target XLSX files and scale manifests are copied to
a backup directory outside the `sub-*/scales` discovery pattern. New XLSX and
JSON files are staged first, then atomically replace their targets. A failure
during replacement restores files from the backup.

## Manifest And Audit

Each scale manifest records the source workbook, source ID, canonical target
subject, `matched_section_count: 1`, `status: matched_baseline_only`, and an
import timestamp. A top-level import report records source/target counts,
written subjects, backup path, and validation failures.

## Verification

Tests cover exact source-ID parsing, rejection of unrelated IDs, canonical
target IDs, baseline-only writes, name exclusion, backup creation, and manifest
updates. After import, the existing scale extractor must find 22 healthy
baseline rows and merge them with fMRI by `sub-YZHC*` directory identity.
