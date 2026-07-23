# Data Foundation Report

- Project: SleepAgent
- Run time: 2026-07-23T03:04:42

## Inputs

- subject_table: `/home/zyb/Agent_skills/SleepAgent/outputs/features/fmri/experiment_plan_cdea5110b79a/fmri_features.csv`
- eeg_features: `__sleepagent_missing_eeg_features__.csv`
- fmri_features: `/home/zyb/Agent_skills/SleepAgent/outputs/features/fmri/experiment_plan_cdea5110b79a/fmri_features.csv`
- dti_features: `__sleepagent_missing_dti_features__.csv`
- mri_features: `__sleepagent_missing_mri_features__.csv`
- scale_features: `__sleepagent_missing_scale_features__.csv`
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

- fMRI: 74

## Highest Missingness Variables

- `thalamus_roi_voxels` (fMRI): 0.247
- `DMN_roi_voxels` (fMRI): 0.247
- `salience_roi_voxels` (fMRI): 0.247
- `frontoparietal_roi_voxels` (fMRI): 0.247
- `thalamus_DMN_FC` (fMRI): 0.247
- `thalamus_salience_FC` (fMRI): 0.247
- `thalamus_frontoparietal_FC` (fMRI): 0.247
- `DMN_salience_FC` (fMRI): 0.247
- `DMN_frontoparietal_FC` (fMRI): 0.247
- `salience_frontoparietal_FC` (fMRI): 0.247
- `DMN_FC` (fMRI): 0.247
- `salience_FC` (fMRI): 0.247
- `frontoparietal_FC` (fMRI): 0.247
- `session` (fMRI): 0.0
- `task` (fMRI): 0.0
- `qc_signal_GS_pre_mean` (fMRI): 0.0
- `qc_signal_GS_post_mean` (fMRI): 0.0
- `qc_signal_GS_mean_delta` (fMRI): 0.0
- `qc_signal_GS_pre_sigma` (fMRI): 0.0
- `qc_signal_GS_post_sigma` (fMRI): 0.0

## Approved Variables

- Total approved variables: 74
- EEG: 0
- fMRI: 26
- DTI: 0
- MRI: 0
- scales: 0
- covariates: 1
- group: 0
- qc: 47

## QC Summary

- pass: 0
- caution: 0
- fail: 0
- unknown: 93

## Multimodal Master Table

- Rows: 93
- Columns: 87
- Input files: 1

## Knowledge Grounding Inputs

- `data/foundation/subject_index.csv`
- `data/foundation/feature_registry.csv`
- `data/foundation/approved_variables.yaml`
- `data/foundation/data_dictionary.yaml`
- `data/foundation/qc_summary.csv`
- `data/foundation/multimodal_master_table.csv`

## Warnings

- None
