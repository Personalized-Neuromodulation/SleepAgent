# Data Foundation Report

- Project: SleepAgent
- Run time: 2026-08-11T03:36:37

## Inputs

- subject_table: `/home/zyb/Agent_skills/SleepAgent/outputs/discovery_loop/iteration_003/features/fmri/pre_experiment_features/fmri_features.csv`
- eeg_features: `__sleepagent_missing_eeg_features__.csv`
- fmri_features: `/home/zyb/Agent_skills/SleepAgent/outputs/discovery_loop/iteration_003/features/fmri/pre_experiment_features/fmri_features.csv`
- dti_features: `__sleepagent_missing_dti_features__.csv`
- mri_features: `__sleepagent_missing_mri_features__.csv`
- scale_features: `/home/zyb/Agent_skills/SleepAgent/outputs/discovery_loop/iteration_003/features/scales/pre_experiment_features/scale_features.csv`
- qc_summary: `__sleepagent_missing_qc_summary__.csv`

## Subjects

- Total subjects: 93
- HC: 0
- INS: 0

## Modality Coverage

- EEG: 0
- fMRI: 93
- DTI: 0
- MRI: 0
- scales: 0

## Feature Counts

- fMRI: 88
- scales: 7

## Highest Missingness Variables

- `session` (fMRI): 0.0
- `task` (fMRI): 0.0
- `qc_signal_GS_pre_mean` (fMRI): 0.0
- `qc_signal_GS_post_mean` (fMRI): 0.0
- `qc_signal_GS_mean_delta` (fMRI): 0.0
- `qc_signal_GS_pre_sigma` (fMRI): 0.0
- `qc_signal_GS_post_sigma` (fMRI): 0.0
- `qc_signal_GS_sigma_delta` (fMRI): 0.0
- `qc_signal_GS_sigma_reduction_percent` (fMRI): 0.0
- `qc_signal_GS_pre_max` (fMRI): 0.0
- `qc_signal_GS_post_max` (fMRI): 0.0
- `qc_signal_CSF_pre_mean` (fMRI): 0.0
- `qc_signal_CSF_post_mean` (fMRI): 0.0
- `qc_signal_CSF_mean_delta` (fMRI): 0.0
- `qc_signal_CSF_pre_sigma` (fMRI): 0.0
- `qc_signal_CSF_post_sigma` (fMRI): 0.0
- `qc_signal_CSF_sigma_delta` (fMRI): 0.0
- `qc_signal_CSF_sigma_reduction_percent` (fMRI): 0.0
- `qc_signal_CSF_pre_max` (fMRI): 0.0
- `qc_signal_CSF_post_max` (fMRI): 0.0

## Approved Variables

- Total approved variables: 95
- EEG: 0
- fMRI: 40
- DTI: 0
- MRI: 0
- scales: 7
- covariates: 1
- group: 0
- qc: 47

## QC Summary

- pass: 0
- caution: 0
- fail: 0
- unknown: 93

## Multimodal Master Table

- Rows: 144
- Columns: 108
- Input files: 2

## Knowledge Grounding Inputs

- `data/foundation/subject_index.csv`
- `data/foundation/feature_registry.csv`
- `data/foundation/approved_variables.yaml`
- `data/foundation/data_dictionary.yaml`
- `data/foundation/qc_summary.csv`
- `data/foundation/multimodal_master_table.csv`

## Warnings

- None
