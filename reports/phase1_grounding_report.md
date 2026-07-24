# Knowledge Grounding Report

## Summary

- Literature records: 1000
- Evidence records: 8681
- Mechanism graph nodes: 9751
- Mechanism graph edges: 34863

## Grounding Corpus Build

- Corpus version: sleepagent_grounding_data_constrained_v1
- Query set version: sleep_literature_queries_v2_broad_sleep_science
- Build time: 2026-07-23T11:16:10.747447+00:00
- API enabled: True
- Providers: none
- Query count: 1
- API raw retrieved count: 7176
- API deduplicated count: 1000
- Final literature count: 1000
- Evidence count: 8681
- High-quality evidence count: 1348
- Mechanism graph nodes: 9751
- Mechanism graph edges: 34863
- Mapped concepts: 1
- Ambiguous concepts: 0
- Unavailable concepts: 20
- Fallback used: False
- Output manifest: /home/zyb/Agent_skills/SleepAgent/outputs/grounding/corpus_manifest.json

## Evidence Direction Counts

- support: 2749
- refute: 16
- null: 73
- unclear: 5843

## Evidence Quality

- min: 0.070
- mean: 0.448
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

- `hyperarousal` candidates=['beta_power', 'anxiety_score']
- `default mode network dysregulation` candidates=[]
- `confound / methodological limitation` candidates=[]
- `white matter integrity` candidates=['FA', 'thalamic_radiation_FA', 'cingulum_FA']
- `salience network dysregulation` candidates=[]
- `insomnia severity` candidates=['ISI', 'PSQI']
- `REM_NREM_switching` candidates=[]
- `circadian_regulation` candidates=[]
- `limbic structural vulnerability` candidates=[]
- `gabaergic_sleep_promotion` candidates=[]
- `sleep quality` candidates=[]
- `spindle generation` candidates=['spindle_density', 'sigma_power']
- `thalamic_reticular_spindle` candidates=[]
- `inflammatory_sleep_regulation` candidates=[]
- `slow-wave generation` candidates=['slow_wave_density', 'delta_power']
- `structural morphology` candidates=[]
- `adenosine_sleep_pressure` candidates=[]
- `orexin_hypocretin_arousal` candidates=[]
- `glymphatic_clearance` candidates=[]
- `cortical_slow_oscillation` candidates=[]

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
- API records before deduplication: 7176
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
- Unavailable theory-only concepts: ['hyperarousal', 'default mode network dysregulation', 'confound / methodological limitation', 'white matter integrity', 'salience network dysregulation', 'insomnia severity', 'REM_NREM_switching', 'circadian_regulation', 'limbic structural vulnerability', 'gabaergic_sleep_promotion', 'sleep quality', 'spindle generation', 'thalamic_reticular_spindle', 'inflammatory_sleep_regulation', 'slow-wave generation', 'structural morphology', 'adenosine_sleep_pressure', 'orexin_hypocretin_arousal', 'glymphatic_clearance', 'cortical_slow_oscillation']
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
- Papers with evidence: 987
- Papers without evidence: 13
- Evidence count: 8681
- Evidence per paper: mean=8.795, median=7.0
- Direction counts: {'unclear': 5843, 'support': 2749, 'null': 73, 'refute': 16}
- Mechanism coverage: {'hyperarousal': 303, 'thalamocortical coupling': 794, 'default mode network dysregulation': 676, 'confound / methodological limitation': 1066, 'white matter integrity': 795, 'salience network dysregulation': 56, 'insomnia severity': 418, 'REM_NREM_switching': 1325, 'circadian_regulation': 129, 'limbic structural vulnerability': 383, 'gabaergic_sleep_promotion': 85, 'sleep quality': 496, 'spindle generation': 577, 'thalamic_reticular_spindle': 565, 'inflammatory_sleep_regulation': 14, 'slow-wave generation': 551, 'structural morphology': 219, 'adenosine_sleep_pressure': 38, 'orexin_hypocretin_arousal': 18, 'glymphatic_clearance': 83, 'cortical_slow_oscillation': 90}
- Mechanisms with zero evidence: []
- Missing variable rate: 0.0
- Missing modality rate: 0.0
- Unclear direction rate: 0.673
- Possible positive evidence bias: False
- Unmatched relevant papers: ['doi:10.3389/fpsyt.2026.1730858', 'doi:10.1038/s41598-021-81219-2', 'doi:10.1016/j.neulet.2025.138313', 'doi:10.3389/fpsyt.2023.1114945', 'doi:10.1111/ene.14784', 'doi:10.1002/hbm.25125', 'doi:10.1093/brain/awq296', 'doi:10.1111/cns.70141', 'doi:10.1002/mco2.70130', 'doi:10.3389/fpain.2025.1609524']

## Evidence Quality and Feasibility

- Mean extraction confidence score: 0.813
- Mean evidence quality score: 0.448
- Mean mechanistic strength score: 0.446
- Mean clinical applicability score: 0.584
- Mean evidence feasibility score: 0.536
- Mean final evidence score: 0.532
- High feasibility evidence count: 2741
- High citation but low feasibility evidence: 100
- High mechanistic but low clinical applicability evidence: 69

## Citation and Journal Metadata

- Citation availability rate: 1.0
- Journal availability rate: 0.917
- Median citation count: 9.0
- Citation source breakdown: {'openalex': 3040, 'semantic_scholar': 3557, 'europe_pmc': 2084}
- Journal metric availability: 0.0
- Note: citation and journal metrics are auxiliary and not primary evidence quality determinants.

## Animal and Translational Evidence

- Human evidence count: 1920
- Animal evidence count: 2419
- Translational evidence count: 3090
- Species distribution: {'human': 1920, 'cat': 494, 'unknown': 4342, 'rat': 1637, 'mixed': 215, 'nonhuman_primate': 4, 'mouse': 69}
- Evidence context distribution: {'human_clinical': 1460, 'human_neuroimaging': 2452, 'animal_mechanistic': 3229, 'human_general_sleep': 1508, 'cellular_molecular': 32}
- Downstream role distribution: {'direct_human_evidence': 3362, 'background_mechanism': 764, 'critique_only': 1026, 'translational_mechanistic_support': 3090, 'not_for_hypothesis_generation': 439}
- Translational risks: {'no_direct_human_measure': 6220, 'non_clinical_model': 713, 'species_difference': 2419, 'small_animal_model': 1706, 'artificial_sleep_deprivation': 118}
- Animal evidence is used for mechanistic plausibility, not direct human clinical support.

## LLM-assisted Evidence Verification

- LLM enabled: False
- Provider: openai
- Model: gpt-4.1-mini
- LLM calls attempted: 0
- LLM calls succeeded: 0
- LLM calls failed: 0
- Rule-only evidence count: 8681
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
