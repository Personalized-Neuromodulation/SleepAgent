# Phase 1 Grounding Report

## Summary

- Literature records: 3
- Evidence records: 14
- Mechanism graph nodes: 54
- Mechanism graph edges: 107

## Evidence Direction Counts

- support: 14
- refute: 0
- null: 0
- unclear: 0

## Evidence Quality

- min: 0.900
- mean: 0.963
- max: 0.980

## Analysis-Ready Variables

- `slow_wave_density` (EEG, role=feature, missing=0.2)
- `spindle_density` (EEG, role=feature, missing=0.0)
- `delta_power` (EEG, role=feature, missing=0.0)
- `beta_power` (EEG, role=feature, missing=0.2)
- `in_scanner_sleep_time` (EEG, role=covariate, missing=0.0)
- `thalamus_DMN_FC` (fMRI, role=feature, missing=0.0)
- `DMN_FC` (fMRI, role=feature, missing=0.0)
- `salience_FC` (fMRI, role=feature, missing=0.2)
- `mean_FD` (fMRI, role=covariate, missing=0.0)
- `thalamic_radiation_FA` (DTI, role=feature, missing=0.0)
- `cingulum_FA` (DTI, role=feature, missing=0.2)
- `FA` (DTI, role=feature, missing=0.0)
- `thalamus_volume` (MRI, role=feature, missing=0.0)
- `hippocampus_volume` (MRI, role=feature, missing=0.0)
- `ISI` (scales, role=outcome, missing=0.0)
- `PSQI` (scales, role=outcome, missing=0.0)
- `anxiety_score` (scales, role=scale, missing=0.0)
- `depression_score` (scales, role=scale, missing=0.0)
- `medication` (scales, role=covariate, missing=0.0)

## Unavailable But Theoretically Relevant Variables

- `structural morphology` candidates=[]
- `thalamic morphology` candidates=[]

## Ambiguous Mappings

- `thalamocortical coupling` approved=['thalamus_DMN_FC', 'thalamic_radiation_FA']
- `hyperarousal` approved=['beta_power', 'anxiety_score']
- `slow-wave generation` approved=['slow_wave_density', 'delta_power']
- `insomnia severity` approved=['ISI', 'PSQI']
- `white matter integrity` approved=['FA', 'thalamic_radiation_FA', 'cingulum_FA']

## Main Confounds

- age
- medication
- sex

## Phase 2 Input Files

- `/home/zyb/Agent_skills/SleepAgent/outputs/grounding/evidence_table.csv`
- `/home/zyb/Agent_skills/SleepAgent/outputs/grounding/evidence_table.json`
- `/home/zyb/Agent_skills/SleepAgent/outputs/grounding/mechanism_graph_nodes.csv`
- `/home/zyb/Agent_skills/SleepAgent/outputs/grounding/mechanism_graph_edges.csv`
- `/home/zyb/Agent_skills/SleepAgent/outputs/grounding/mechanism_graph.json`
- `/home/zyb/Agent_skills/SleepAgent/outputs/grounding/evidence_to_variable_map.yaml`
- `/home/zyb/Agent_skills/SleepAgent/outputs/grounding/approved_variables_from_grounding.yaml`
- `/home/zyb/Agent_skills/SleepAgent/outputs/profiles/theoretical_profile.yaml`
- `/home/zyb/Agent_skills/SleepAgent/outputs/profiles/observed_profile.yaml`
- `/home/zyb/Agent_skills/SleepAgent/outputs/profiles/analysis_ready_profile.yaml`
