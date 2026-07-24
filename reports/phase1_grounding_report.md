# Knowledge Grounding Report

## Summary

- Literature records: 1000
- Evidence records: 7755
- Mechanism graph nodes: 8809
- Mechanism graph edges: 31153

## Grounding Corpus Build

- Corpus version: sleepagent_grounding_data_constrained_v1
- Query set version: sleep_literature_queries_v2_broad_sleep_science
- Build time: 2026-07-24T07:35:59.583837+00:00
- API enabled: True
- Providers: none
- Query count: 1
- API raw retrieved count: 8526
- API deduplicated count: 1000
- Final literature count: 1000
- Evidence count: 7755
- High-quality evidence count: 1118
- Mechanism graph nodes: 8809
- Mechanism graph edges: 31153
- Mapped concepts: 1
- Ambiguous concepts: 0
- Unavailable concepts: 20
- Fallback used: False
- Output manifest: /home/zyb/Agent_skills/SleepAgent/outputs/grounding/corpus_manifest.json

## Evidence Direction Counts

- support: 2444
- refute: 6
- null: 81
- unclear: 5224

## Evidence Quality

- min: 0.070
- mean: 0.433
- max: 1.000

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

- `confound / methodological limitation` candidates=[]
- `default mode network dysregulation` candidates=[]
- `REM_NREM_switching` candidates=[]
- `structural morphology` candidates=[]
- `white matter integrity` candidates=['FA', 'thalamic_radiation_FA', 'cingulum_FA']
- `hyperarousal` candidates=['beta_power', 'anxiety_score']
- `limbic structural vulnerability` candidates=[]
- `orexin_hypocretin_arousal` candidates=[]
- `insomnia severity` candidates=['ISI', 'PSQI']
- `salience network dysregulation` candidates=[]
- `circadian_regulation` candidates=[]
- `sleep quality` candidates=[]
- `slow-wave generation` candidates=['slow_wave_density', 'delta_power']
- `cortical_slow_oscillation` candidates=[]
- `spindle generation` candidates=['spindle_density', 'sigma_power']
- `thalamic_reticular_spindle` candidates=[]
- `adenosine_sleep_pressure` candidates=[]
- `glymphatic_clearance` candidates=[]
- `gabaergic_sleep_promotion` candidates=[]
- `inflammatory_sleep_regulation` candidates=[]

## Ambiguous Mappings


## Main Confounds

- age
- medication
- sex

## API Literature Retrieval

- API enabled: True
- Providers used: literature_db_rag
- Search query count: 1
- Records retrieved per provider: {'literature_db_rag': 1000}
- Provider-level results:
  - PubMed: 0
  - Europe PMC: 0
  - OpenAlex: 0
  - Semantic Scholar: 0
- API records before deduplication: 8526
- API records after deduplication: 1000
- Final literature count: 1000
- API errors: none
- API warnings: none
- Cache enabled: False
- Cache hit count if available: unavailable
- Cache directory: 

## Data Grounding

- Analysis-ready features: 74
- Mapped variables: ['thalamus_DMN_FC']
- Unavailable theory-only concepts: ['confound / methodological limitation', 'default mode network dysregulation', 'REM_NREM_switching', 'structural morphology', 'white matter integrity', 'hyperarousal', 'limbic structural vulnerability', 'orexin_hypocretin_arousal', 'insomnia severity', 'salience network dysregulation', 'circadian_regulation', 'sleep quality', 'slow-wave generation', 'cortical_slow_oscillation', 'spindle generation', 'thalamic_reticular_spindle', 'adenosine_sleep_pressure', 'glymphatic_clearance', 'gabaergic_sleep_promotion', 'inflammatory_sleep_regulation']
- Major confounds:
  - mean_FD
  - in_scanner_sleep_time
  - medication
  - age
  - sex

## Grounding QC

- Passed: True
- Warnings: none
- Errors: none
- Recommended next steps: none

## Evidence Extraction Completeness

- Total papers: 1000
- Papers with evidence: 973
- Papers without evidence: 27
- Evidence count: 7755
- Evidence per paper: mean=7.97, median=7.0
- Direction counts: {'unclear': 5224, 'support': 2444, 'null': 81, 'refute': 6}
- Mechanism coverage: {'confound / methodological limitation': 1423, 'default mode network dysregulation': 591, 'thalamocortical coupling': 360, 'REM_NREM_switching': 1185, 'structural morphology': 275, 'white matter integrity': 867, 'hyperarousal': 212, 'limbic structural vulnerability': 415, 'orexin_hypocretin_arousal': 15, 'insomnia severity': 426, 'salience network dysregulation': 58, 'circadian_regulation': 148, 'sleep quality': 570, 'slow-wave generation': 390, 'cortical_slow_oscillation': 46, 'spindle generation': 317, 'thalamic_reticular_spindle': 273, 'adenosine_sleep_pressure': 35, 'glymphatic_clearance': 120, 'gabaergic_sleep_promotion': 19, 'inflammatory_sleep_regulation': 10}
- Mechanisms with zero evidence: []
- Missing variable rate: 0.0
- Missing modality rate: 0.0
- Unclear direction rate: 0.674
- Possible positive evidence bias: False
- Unmatched relevant papers: ['doi:10.1038/s41467-023-43737-7', 'doi:10.1101/2023.05.13.540646', 'doi:10.3389/fneur.2022.966659', 'doi:10.5498/wjp.v14.i2.315', 'doi:10.1038/s41598-022-22652-9', 'doi:10.1002/hbm.25125', 'doi:10.1038/s41598-021-81219-2', 'doi:10.3389/fpsyt.2026.1730858', 'doi:10.1371/journal.pbio.3003633', 'doi:10.3389/fpain.2025.1609524']

## Evidence Quality and Feasibility

- Mean extraction confidence score: 0.812
- Mean evidence quality score: 0.433
- Mean mechanistic strength score: 0.436
- Mean clinical applicability score: 0.586
- Mean evidence feasibility score: 0.518
- Mean final evidence score: 0.522
- High feasibility evidence count: 2356
- High citation but low feasibility evidence: 176
- High mechanistic but low clinical applicability evidence: 8

## Citation and Journal Metadata

- Citation availability rate: 1.0
- Journal availability rate: 0.896
- Median citation count: 7.0
- Citation source breakdown: {'europe_pmc': 2137, 'openalex': 2547, 'semantic_scholar': 3071}
- Journal metric availability: 0.0
- Note: citation and journal metrics are auxiliary and not primary evidence quality determinants.

## Animal and Translational Evidence

- Human evidence count: 1626
- Animal evidence count: 2206
- Translational evidence count: 2481
- Species distribution: {'mixed': 176, 'unknown': 3923, 'human': 1626, 'cat': 497, 'rat': 1509, 'mouse': 22, 'nonhuman_primate': 2}
- Evidence context distribution: {'human_neuroimaging': 2563, 'human_clinical': 1327, 'animal_mechanistic': 2702, 'human_general_sleep': 1137, 'cellular_molecular': 26}
- Downstream role distribution: {'background_mechanism': 836, 'direct_human_evidence': 2818, 'translational_mechanistic_support': 2481, 'critique_only': 1271, 'not_for_hypothesis_generation': 349}
- Translational risks: {'no_direct_human_measure': 5550, 'non_clinical_model': 675, 'species_difference': 2206, 'small_animal_model': 1531, 'artificial_sleep_deprivation': 122}
- Animal evidence is used for mechanistic plausibility, not direct human clinical support.

## LLM-assisted Evidence Verification

- LLM enabled: False
- Provider: openai
- Model: gpt-4.1-mini
- LLM calls attempted: 0
- LLM calls succeeded: 0
- LLM calls failed: 0
- Rule-only evidence count: 7755
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
