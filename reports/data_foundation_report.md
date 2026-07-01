# Data Foundation Report

- Project: SleepAgent
- Run time: 2026-07-01T06:06:48

## Inputs

- subject_table: `data/fixtures/toy_subject_index.csv`
- eeg_features: `data/fixtures/toy_eeg_features.csv`
- fmri_features: `data/fixtures/toy_fmri_features.csv`
- dti_features: `data/fixtures/toy_dti_features.csv`
- mri_features: `data/fixtures/toy_mri_features.csv`
- scale_features: `data/fixtures/toy_scale_features.csv`
- qc_summary: `data/fixtures/toy_qc_summary.csv`

## Subjects

- Total subjects: 5
- HC: 2
- INS: 3

## Modality Coverage

- EEG: 5
- fMRI: 5
- DTI: 5
- MRI: 5
- scales: 5

## Feature Counts

- DTI: 3
- EEG: 5
- MRI: 2
- fMRI: 4
- scales: 5

## Highest Missingness Variables

- `slow_wave_density` (EEG): 0.2
- `beta_power` (EEG): 0.2
- `salience_FC` (fMRI): 0.2
- `cingulum_FA` (DTI): 0.2
- `spindle_density` (EEG): 0.0
- `delta_power` (EEG): 0.0
- `in_scanner_sleep_time` (EEG): 0.0
- `thalamus_DMN_FC` (fMRI): 0.0
- `DMN_FC` (fMRI): 0.0
- `mean_FD` (fMRI): 0.0
- `thalamic_radiation_FA` (DTI): 0.0
- `FA` (DTI): 0.0
- `thalamus_volume` (MRI): 0.0
- `hippocampus_volume` (MRI): 0.0
- `ISI` (scales): 0.0
- `PSQI` (scales): 0.0
- `anxiety_score` (scales): 0.0
- `depression_score` (scales): 0.0
- `medication` (scales): 0.0

## Approved Variables

- Total approved variables: 19
- EEG: 4
- fMRI: 3
- DTI: 3
- MRI: 2
- scales: 4
- covariates: 3
- group: 0
- qc: 0

## QC Summary

- pass: 14
- caution: 2
- fail: 1
- unknown: 0

## Multimodal Master Table

- Rows: 5
- Columns: 31
- Input files: 5

## Knowledge Grounding Inputs

- `data/foundation/subject_index.csv`
- `data/foundation/feature_registry.csv`
- `data/foundation/approved_variables.yaml`
- `data/foundation/data_dictionary.yaml`
- `data/foundation/qc_summary.csv`
- `data/foundation/multimodal_master_table.csv`

## Warnings

- QC failures present: 1 records
