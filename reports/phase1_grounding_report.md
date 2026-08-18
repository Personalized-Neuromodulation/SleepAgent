# Knowledge Grounding Report

## Summary

- Literature records: 1000
- Evidence records: 7987
- Mechanism graph nodes: 9048
- Mechanism graph edges: 32081

## Grounding Corpus Build

- Corpus version: sleepagent_grounding_data_constrained_v1
- Query set version: sleep_literature_queries_v2_broad_sleep_science
- Build time: 2026-08-11T07:44:32.339651+00:00
- API enabled: True
- Providers: none
- Query count: 1
- API raw retrieved count: 15321
- API deduplicated count: 1000
- Final literature count: 1000
- Evidence count: 7987
- High-quality evidence count: 1373
- Mechanism graph nodes: 9048
- Mechanism graph edges: 32081
- Mapped concepts: 1
- Ambiguous concepts: 0
- Unavailable concepts: 20
- Fallback used: False
- Output manifest: /home/zyb/Agent_skills/SleepAgent/outputs/grounding/corpus_manifest.json

## Evidence Direction Counts

- support: 2727
- refute: 3
- null: 94
- unclear: 5163

## Evidence Quality

- min: 0.061
- mean: 0.473
- max: 1.000

## Analysis-Ready Variables

- `session` (fMRI, role=feature, missing=0.354)
- `task` (fMRI, role=feature, missing=0.354)
- `qc_signal_GS_pre_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_GS_post_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_GS_mean_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_GS_pre_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_GS_post_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_GS_sigma_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_GS_sigma_reduction_percent` (fMRI, role=qc, missing=0.354)
- `qc_signal_GS_pre_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_GS_post_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_pre_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_post_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_mean_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_pre_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_post_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_sigma_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_sigma_reduction_percent` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_pre_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_CSF_post_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_pre_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_post_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_mean_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_pre_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_post_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_sigma_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_sigma_reduction_percent` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_pre_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_WM_post_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_pre_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_post_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_mean_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_pre_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_post_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_sigma_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_sigma_reduction_percent` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_pre_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_DVARS_post_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_pre_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_post_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_mean_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_pre_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_post_sigma` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_sigma_delta` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_sigma_reduction_percent` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_pre_max` (fMRI, role=qc, missing=0.354)
- `qc_signal_FD_post_max` (fMRI, role=qc, missing=0.354)
- `mean_FD` (fMRI, role=covariate, missing=0.354)
- `max_FD` (fMRI, role=feature, missing=0.354)
- `mean_DVARS` (fMRI, role=feature, missing=0.354)
- `qc_signal_post_DVARS_mean` (fMRI, role=qc, missing=0.354)
- `qc_signal_post_GS_mean` (fMRI, role=qc, missing=0.354)
- `percent_high_motion` (fMRI, role=feature, missing=0.354)
- `post_DVARS_std` (fMRI, role=feature, missing=0.354)
- `timefreq_TR` (fMRI, role=feature, missing=0.354)
- `timefreq_sampling_rate_hz` (fMRI, role=feature, missing=0.354)
- `timefreq_ALFF_0.01_0.08` (fMRI, role=feature, missing=0.354)
- `timefreq_fALFF_0.01_0.08_over_0.01_0.25` (fMRI, role=feature, missing=0.354)
- `global_signal_psd_power_mean` (fMRI, role=feature, missing=0.354)
- `global_signal_psd_power_max` (fMRI, role=feature, missing=0.354)
- `roi_fc_status` (fMRI, role=feature, missing=0.354)
- `roi_coord_source` (fMRI, role=feature, missing=0.354)
- `roi_coord_space` (fMRI, role=feature, missing=0.354)
- `thalamus_roi_voxels` (fMRI, role=feature, missing=0.354)
- `DMN_roi_voxels` (fMRI, role=feature, missing=0.354)
- `salience_roi_voxels` (fMRI, role=feature, missing=0.354)
- `frontoparietal_roi_voxels` (fMRI, role=feature, missing=0.354)
- `thalamus_coord_x` (fMRI, role=feature, missing=0.354)
- `thalamus_coord_y` (fMRI, role=feature, missing=0.354)
- `thalamus_coord_z` (fMRI, role=feature, missing=0.354)
- `DMN_coord_x` (fMRI, role=feature, missing=0.354)
- `DMN_coord_y` (fMRI, role=feature, missing=0.354)
- `DMN_coord_z` (fMRI, role=feature, missing=0.354)
- `salience_coord_x` (fMRI, role=feature, missing=0.354)
- `salience_coord_y` (fMRI, role=feature, missing=0.354)
- `salience_coord_z` (fMRI, role=feature, missing=0.354)
- `frontoparietal_coord_x` (fMRI, role=feature, missing=0.354)
- `frontoparietal_coord_y` (fMRI, role=feature, missing=0.354)
- `frontoparietal_coord_z` (fMRI, role=feature, missing=0.354)
- `thalamus_DMN_FC` (fMRI, role=feature, missing=0.354)
- `thalamus_salience_FC` (fMRI, role=feature, missing=0.354)
- `thalamus_frontoparietal_FC` (fMRI, role=feature, missing=0.354)
- `DMN_salience_FC` (fMRI, role=feature, missing=0.354)
- `DMN_frontoparietal_FC` (fMRI, role=feature, missing=0.354)
- `salience_frontoparietal_FC` (fMRI, role=feature, missing=0.354)
- `DMN_FC` (fMRI, role=feature, missing=0.354)
- `salience_FC` (fMRI, role=feature, missing=0.354)
- `frontoparietal_FC` (fMRI, role=feature, missing=0.354)

## Unavailable But Theoretically Relevant Variables

- `hyperarousal` candidates=['beta_power', 'anxiety_score']
- `default mode network dysregulation` candidates=[]
- `confound / methodological limitation` candidates=[]
- `salience network dysregulation` candidates=[]
- `insomnia severity` candidates=['ISI', 'PSQI']
- `white matter integrity` candidates=['FA', 'thalamic_radiation_FA', 'cingulum_FA']
- `REM_NREM_switching` candidates=[]
- `circadian_regulation` candidates=[]
- `limbic structural vulnerability` candidates=[]
- `sleep quality` candidates=[]
- `slow-wave generation` candidates=['slow_wave_density', 'delta_power']
- `thalamic_reticular_spindle` candidates=[]
- `structural morphology` candidates=[]
- `orexin_hypocretin_arousal` candidates=[]
- `glymphatic_clearance` candidates=[]
- `adenosine_sleep_pressure` candidates=[]
- `gabaergic_sleep_promotion` candidates=[]
- `spindle generation` candidates=['spindle_density', 'sigma_power']
- `cortical_slow_oscillation` candidates=[]
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
- API records before deduplication: 15321
- API records after deduplication: 1000
- Final literature count: 1000
- API errors: none
- API warnings: none
- Cache enabled: False
- Cache hit count if available: unavailable
- Cache directory: 

## Data Grounding

- Analysis-ready features: 88
- Mapped variables: ['thalamus_DMN_FC']
- Unavailable theory-only concepts: ['hyperarousal', 'default mode network dysregulation', 'confound / methodological limitation', 'salience network dysregulation', 'insomnia severity', 'white matter integrity', 'REM_NREM_switching', 'circadian_regulation', 'limbic structural vulnerability', 'sleep quality', 'slow-wave generation', 'thalamic_reticular_spindle', 'structural morphology', 'orexin_hypocretin_arousal', 'glymphatic_clearance', 'adenosine_sleep_pressure', 'gabaergic_sleep_promotion', 'spindle generation', 'cortical_slow_oscillation', 'inflammatory_sleep_regulation']
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
- Papers with evidence: 980
- Papers without evidence: 20
- Evidence count: 7987
- Evidence per paper: mean=8.15, median=7.0
- Direction counts: {'unclear': 5163, 'support': 2727, 'null': 94, 'refute': 3}
- Mechanism coverage: {'hyperarousal': 240, 'thalamocortical coupling': 697, 'default mode network dysregulation': 990, 'confound / methodological limitation': 1036, 'salience network dysregulation': 89, 'insomnia severity': 563, 'white matter integrity': 1023, 'REM_NREM_switching': 1039, 'circadian_regulation': 97, 'limbic structural vulnerability': 499, 'sleep quality': 691, 'slow-wave generation': 207, 'thalamic_reticular_spindle': 150, 'structural morphology': 309, 'orexin_hypocretin_arousal': 18, 'glymphatic_clearance': 85, 'adenosine_sleep_pressure': 18, 'gabaergic_sleep_promotion': 33, 'spindle generation': 170, 'cortical_slow_oscillation': 21, 'inflammatory_sleep_regulation': 12}
- Mechanisms with zero evidence: []
- Missing variable rate: 0.0
- Missing modality rate: 0.0
- Unclear direction rate: 0.646
- Possible positive evidence bias: False
- Unmatched relevant papers: ['doi:10.3389/fpsyt.2026.1730858', 'doi:10.1038/s41598-022-22652-9', 'doi:10.1038/s41598-021-81219-2', 'doi:10.5498/wjp.v14.i2.315', 'doi:10.1111/ene.14784', 'doi:10.1101/2023.05.13.540646', 'doi:10.1038/s41467-023-43737-7', 'doi:10.1002/hbm.25125', 'doi:10.1016/j.neuron.2025.02.004', 'doi:10.5772/intechopen.73846']

## Evidence Quality and Feasibility

- Mean extraction confidence score: 0.82
- Mean evidence quality score: 0.473
- Mean mechanistic strength score: 0.424
- Mean clinical applicability score: 0.621
- Mean evidence feasibility score: 0.581
- Mean final evidence score: 0.547
- High feasibility evidence count: 3035
- High citation but low feasibility evidence: 57
- High mechanistic but low clinical applicability evidence: 15

## Citation and Journal Metadata

- Citation availability rate: 1.0
- Journal availability rate: 0.928
- Median citation count: 9.0
- Citation source breakdown: {'europe_pmc': 2439, 'openalex': 2815, 'semantic_scholar': 2733}
- Journal metric availability: 0.0
- Note: citation and journal metrics are auxiliary and not primary evidence quality determinants.

## Animal and Translational Evidence

- Human evidence count: 2222
- Animal evidence count: 2055
- Translational evidence count: 2212
- Species distribution: {'human': 2222, 'cat': 465, 'rat': 1405, 'unknown': 3710, 'mixed': 177, 'mouse': 5, 'nonhuman_primate': 3}
- Evidence context distribution: {'human_clinical': 1811, 'human_neuroimaging': 2816, 'animal_mechanistic': 2353, 'human_general_sleep': 988, 'cellular_molecular': 19}
- Downstream role distribution: {'direct_human_evidence': 3527, 'critique_only': 1055, 'translational_mechanistic_support': 2212, 'not_for_hypothesis_generation': 409, 'background_mechanism': 784}
- Translational risks: {'no_direct_human_measure': 5139, 'non_clinical_model': 645, 'species_difference': 2055, 'small_animal_model': 1410, 'artificial_sleep_deprivation': 123}
- Animal evidence is used for mechanistic plausibility, not direct human clinical support.

## LLM-assisted Evidence Verification

- LLM enabled: False
- Provider: openai
- Model: gpt-4.1-mini
- LLM calls attempted: 0
- LLM calls succeeded: 0
- LLM calls failed: 0
- Rule-only evidence count: 7987
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
