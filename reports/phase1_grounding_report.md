# Knowledge Grounding Report

## Summary

- Literature records: 20
- Evidence records: 412
- Mechanism graph nodes: 471
- Mechanism graph edges: 1694

## Grounding Corpus Build

- Corpus version: sleepagent_grounding_data_constrained_v1
- Query set version: sleep_literature_queries_v2_broad_sleep_science
- Build time: 2026-07-23T07:06:18.600336+00:00
- API enabled: True
- Providers: none
- Query count: 1
- API raw retrieved count: 6895
- API deduplicated count: 20
- Final literature count: 20
- Evidence count: 412
- High-quality evidence count: 51
- Mechanism graph nodes: 471
- Mechanism graph edges: 1694
- Mapped concepts: 1
- Ambiguous concepts: 0
- Unavailable concepts: 10
- Fallback used: False
- Output manifest: /home/zyb/Agent_skills/SleepAgent/outputs/grounding/corpus_manifest.json

## Evidence Direction Counts

- support: 95
- refute: 0
- null: 0
- unclear: 317

## Evidence Quality

- min: 0.170
- mean: 0.408
- max: 0.838

## Analysis-Ready Variables

- `session` (fMRI, role=feature, missing=0.0)
- `task` (fMRI, role=feature, missing=0.0)
- `qc_signal_GS_pre_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_GS_post_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_GS_mean_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_GS_pre_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_GS_post_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_GS_sigma_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_GS_sigma_reduction_percent` (fMRI, role=qc, missing=0.0)
- `qc_signal_GS_pre_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_GS_post_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_pre_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_post_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_mean_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_pre_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_post_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_sigma_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_sigma_reduction_percent` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_pre_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_CSF_post_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_pre_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_post_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_mean_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_pre_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_post_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_sigma_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_sigma_reduction_percent` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_pre_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_WM_post_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_pre_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_post_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_mean_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_pre_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_post_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_sigma_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_sigma_reduction_percent` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_pre_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_DVARS_post_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_pre_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_post_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_mean_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_pre_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_post_sigma` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_sigma_delta` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_sigma_reduction_percent` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_pre_max` (fMRI, role=qc, missing=0.0)
- `qc_signal_FD_post_max` (fMRI, role=qc, missing=0.0)
- `mean_FD` (fMRI, role=covariate, missing=0.0)
- `max_FD` (fMRI, role=feature, missing=0.0)
- `mean_DVARS` (fMRI, role=feature, missing=0.0)
- `qc_signal_post_DVARS_mean` (fMRI, role=qc, missing=0.0)
- `qc_signal_post_GS_mean` (fMRI, role=qc, missing=0.0)
- `percent_high_motion` (fMRI, role=feature, missing=0.0)
- `post_DVARS_std` (fMRI, role=feature, missing=0.0)
- `timefreq_TR` (fMRI, role=feature, missing=0.0)
- `timefreq_sampling_rate_hz` (fMRI, role=feature, missing=0.0)
- `timefreq_ALFF_0.01_0.08` (fMRI, role=feature, missing=0.0)
- `timefreq_fALFF_0.01_0.08_over_0.01_0.25` (fMRI, role=feature, missing=0.0)
- `global_signal_psd_power_mean` (fMRI, role=feature, missing=0.0)
- `global_signal_psd_power_max` (fMRI, role=feature, missing=0.0)
- `roi_fc_status` (fMRI, role=feature, missing=0.0)
- `thalamus_roi_voxels` (fMRI, role=feature, missing=0.247)
- `DMN_roi_voxels` (fMRI, role=feature, missing=0.247)
- `salience_roi_voxels` (fMRI, role=feature, missing=0.247)
- `frontoparietal_roi_voxels` (fMRI, role=feature, missing=0.247)
- `thalamus_DMN_FC` (fMRI, role=feature, missing=0.247)
- `thalamus_salience_FC` (fMRI, role=feature, missing=0.247)
- `thalamus_frontoparietal_FC` (fMRI, role=feature, missing=0.247)
- `DMN_salience_FC` (fMRI, role=feature, missing=0.247)
- `DMN_frontoparietal_FC` (fMRI, role=feature, missing=0.247)
- `salience_frontoparietal_FC` (fMRI, role=feature, missing=0.247)
- `DMN_FC` (fMRI, role=feature, missing=0.247)
- `salience_FC` (fMRI, role=feature, missing=0.247)
- `frontoparietal_FC` (fMRI, role=feature, missing=0.247)

## Unavailable But Theoretically Relevant Variables

- `slow-wave generation` candidates=['slow_wave_density', 'delta_power']
- `spindle generation` candidates=['spindle_density', 'sigma_power']
- `thalamic_reticular_spindle` candidates=[]
- `cortical_slow_oscillation` candidates=[]
- `white matter integrity` candidates=['FA', 'thalamic_radiation_FA', 'cingulum_FA']
- `REM_NREM_switching` candidates=[]
- `confound / methodological limitation` candidates=[]
- `insomnia severity` candidates=['ISI', 'PSQI']
- `default mode network dysregulation` candidates=[]
- `limbic structural vulnerability` candidates=[]

## Ambiguous Mappings


## Main Confounds

- age
- medication
- sex

## API Literature Retrieval

- API enabled: True
- Providers used: literature_db_rag
- Search query count: 1
- Records retrieved per provider: {'literature_db_rag': 20}
- Provider-level results:
  - PubMed: 0
  - Europe PMC: 0
  - OpenAlex: 0
  - Semantic Scholar: 0
- API records before deduplication: 6895
- API records after deduplication: 20
- Final literature count: 20
- API errors: none
- API warnings: none
- Cache enabled: False
- Cache hit count if available: unavailable
- Cache directory: 

## Data Grounding

- Analysis-ready features: 74
- Mapped variables: ['thalamus_DMN_FC']
- Unavailable theory-only concepts: ['slow-wave generation', 'spindle generation', 'thalamic_reticular_spindle', 'cortical_slow_oscillation', 'white matter integrity', 'REM_NREM_switching', 'confound / methodological limitation', 'insomnia severity', 'default mode network dysregulation', 'limbic structural vulnerability']
- Major confounds:
  - mean_FD
  - in_scanner_sleep_time
  - medication
  - age
  - sex

## Grounding QC

- Passed: False
- Warnings: final literature count below 100; preferred mechanism coverage gaps detected; possible positive evidence bias
- Errors: none
- Recommended next steps: Review query coverage or API availability before using this corpus for benchmark work.; Add targeted online queries for mechanisms listed in check_mechanism_coverage.gaps.; Review query set and extraction rules for null/refuting findings.

## Evidence Extraction Completeness

- Total papers: 20
- Papers with evidence: 20
- Papers without evidence: 0
- Evidence count: 412
- Evidence per paper: mean=20.6, median=21.0
- Direction counts: {'unclear': 317, 'support': 95}
- Mechanism coverage: {'slow-wave generation': 25, 'spindle generation': 132, 'thalamocortical coupling': 58, 'thalamic_reticular_spindle': 127, 'cortical_slow_oscillation': 8, 'white matter integrity': 24, 'REM_NREM_switching': 24, 'confound / methodological limitation': 5, 'insomnia severity': 6, 'default mode network dysregulation': 1, 'limbic structural vulnerability': 2}
- Mechanisms with zero evidence: ['hyperarousal', 'salience network dysregulation']
- Missing variable rate: 0.0
- Missing modality rate: 0.0
- Unclear direction rate: 0.769
- Possible positive evidence bias: True
- Unmatched relevant papers: []

## Evidence Quality and Feasibility

- Mean extraction confidence score: 0.782
- Mean evidence quality score: 0.408
- Mean mechanistic strength score: 0.502
- Mean clinical applicability score: 0.508
- Mean evidence feasibility score: 0.504
- Mean final evidence score: 0.516
- High feasibility evidence count: 75
- High citation but low feasibility evidence: 24
- High mechanistic but low clinical applicability evidence: 8

## Citation and Journal Metadata

- Citation availability rate: 1.0
- Journal availability rate: 1.0
- Median citation count: 19.0
- Citation source breakdown: {'semantic_scholar': 170, 'openalex': 150, 'europe_pmc': 92}
- Journal metric availability: 0.0
- Note: citation and journal metrics are auxiliary and not primary evidence quality determinants.

## Animal and Translational Evidence

- Human evidence count: 34
- Animal evidence count: 148
- Translational evidence count: 203
- Species distribution: {'unknown': 230, 'cat': 22, 'rat': 94, 'human': 34, 'mixed': 24, 'mouse': 8}
- Evidence context distribution: {'human_general_sleep': 135, 'human_neuroimaging': 54, 'animal_mechanistic': 218, 'human_clinical': 5}
- Downstream role distribution: {'direct_human_evidence': 145, 'translational_mechanistic_support': 203, 'background_mechanism': 23, 'not_for_hypothesis_generation': 34, 'critique_only': 7}
- Translational risks: {'no_direct_human_measure': 373, 'non_clinical_model': 46, 'species_difference': 148, 'small_animal_model': 102}
- Animal evidence is used for mechanistic plausibility, not direct human clinical support.

## LLM-assisted Evidence Verification

- LLM enabled: False
- Provider: openai
- Model: gpt-4.1-mini
- LLM calls attempted: 0
- LLM calls succeeded: 0
- LLM calls failed: 0
- Rule-only evidence count: 412
- LLM-verified evidence count: 0
- LLM-revised evidence count: 0
- LLM split claim count: 0
- LLM excluded claim count: 0
- Excluded evidence log: /home/zyb/Agent_skills/SleepAgent/outputs/grounding/excluded_evidence_log.jsonl
- Failure fallback used: False

## Evidence Extraction Benchmark

- Mode: not_run
- Mechanism recall: 0
- Mechanism precision: 0
- Direction accuracy: 0
- Modality accuracy: 0
- Species accuracy: 0
- Evidence context accuracy: 0
- Downstream role accuracy: 0
- Paper coverage: 0
- Hallucinated evidence count: 0

## Scientific Loop Input Files

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
