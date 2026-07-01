# Knowledge Grounding Report

## Summary

- Literature records: 3
- Evidence records: 15
- Mechanism graph nodes: 70
- Mechanism graph edges: 154

## Grounding Corpus Build

- Corpus version: sleepagent_grounding_corpus_v1
- Query set version: 
- Build time: 2026-07-01T06:44:54.252350+00:00
- API enabled: False
- Providers: pubmed, europe_pmc, openalex, semantic_scholar
- Query count: 0
- Seed literature count: 3
- API raw retrieved count: 0
- API deduplicated count: 0
- Final literature count: 3
- Evidence count: 15
- High-quality evidence count: 9
- Mechanism graph nodes: 70
- Mechanism graph edges: 154
- Mapped concepts: 1
- Ambiguous concepts: 6
- Unavailable concepts: 4
- Fallback used: True
- Output manifest: /home/jwj/code/SleepAgent/outputs/grounding/corpus_manifest.json

## Evidence Direction Counts

- support: 13
- refute: 0
- null: 0
- unclear: 2

## Evidence Quality

- min: 0.110
- mean: 0.577
- max: 0.830

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

- `confound / methodological limitation` candidates=[]
- `sleep quality` candidates=[]
- `thalamic_reticular_spindle` candidates=[]
- `structural morphology` candidates=[]

## Ambiguous Mappings

- `hyperarousal` approved=['beta_power', 'anxiety_score']
- `thalamocortical coupling` approved=['thalamus_DMN_FC', 'thalamic_radiation_FA']
- `default mode network dysregulation` approved=['DMN_FC', 'thalamus_DMN_FC']
- `white matter integrity` approved=['FA', 'thalamic_radiation_FA', 'cingulum_FA']
- `insomnia severity` approved=['ISI', 'PSQI']
- `slow-wave generation` approved=['slow_wave_density', 'delta_power']

## Main Confounds

- age
- in_scanner_sleep_time
- mean_FD
- medication
- sex

## API Literature Retrieval

- API enabled: False
- Providers used: none
- Search query count: 0
- Records retrieved per provider: {}
- Provider-level results:
  - PubMed: 0
  - Europe PMC: 0
  - OpenAlex: 0
  - Semantic Scholar: 0
- API records before deduplication: 0
- API records after deduplication: 0
- Seed literature count: 3
- Final literature count: 3
- API errors: none
- API warnings: none
- Cache enabled: False
- Cache hit count if available: unavailable
- Cache directory: 

## Data Grounding

- Analysis-ready features: 19
- Mapped variables: ['DMN_FC', 'FA', 'ISI', 'PSQI', 'anxiety_score', 'beta_power', 'cingulum_FA', 'delta_power', 'slow_wave_density', 'spindle_density', 'thalamic_radiation_FA', 'thalamus_DMN_FC']
- Unavailable theory-only concepts: ['confound / methodological limitation', 'sleep quality', 'thalamic_reticular_spindle', 'structural morphology']
- Major confounds:
  - mean_FD
  - in_scanner_sleep_time
  - medication
  - age
  - sex

## Grounding QC

- Passed: False
- Warnings: final literature count below 100; evidence count below 50; preferred mechanism coverage gaps detected; possible positive evidence bias
- Errors: none
- Recommended next steps: Review query coverage or API availability before using this corpus for benchmark work.; Inspect extraction rules and seed/API literature coverage.; Add targeted queries or seed papers for mechanisms listed in check_mechanism_coverage.gaps.; Review query set and extraction rules for null/refuting findings.

## Evidence Extraction Completeness

- Total papers: 3
- Papers with evidence: 3
- Papers without evidence: 0
- Evidence count: 15
- Evidence per paper: mean=5.0, median=5.0
- Direction counts: {'support': 13, 'unclear': 2}
- Mechanism coverage: {'hyperarousal': 1, 'thalamocortical coupling': 2, 'default mode network dysregulation': 1, 'white matter integrity': 2, 'insomnia severity': 2, 'confound / methodological limitation': 2, 'slow-wave generation': 1, 'spindle generation': 1, 'sleep quality': 1, 'thalamic_reticular_spindle': 1, 'structural morphology': 1}
- Mechanisms with zero evidence: ['salience network dysregulation', 'limbic structural vulnerability']
- Missing variable rate: 0.0
- Missing modality rate: 0.0
- Unclear direction rate: 0.133
- Possible positive evidence bias: True
- Unmatched relevant papers: []

## Evidence Quality and Feasibility

- Mean extraction confidence score: 0.947
- Mean evidence quality score: 0.577
- Mean mechanistic strength score: 0.47
- Mean clinical applicability score: 0.807
- Mean evidence feasibility score: 0.775
- Mean final evidence score: 0.663
- High feasibility evidence count: 11
- High citation but low feasibility evidence: 0
- High mechanistic but low clinical applicability evidence: 0

## Citation and Journal Metadata

- Citation availability rate: 0.0
- Journal availability rate: 0.0
- Median citation count: 0.0
- Citation source breakdown: {'missing': 15}
- Journal metric availability: 0.0
- Note: citation and journal metrics are auxiliary and not primary evidence quality determinants.

## Animal and Translational Evidence

- Human evidence count: 9
- Animal evidence count: 4
- Translational evidence count: 4
- Species distribution: {'human': 9, 'unknown': 2, 'rat': 4}
- Evidence context distribution: {'human_neuroimaging': 11, 'animal_mechanistic': 4}
- Downstream role distribution: {'direct_human_evidence': 8, 'critique_only': 2, 'translational_mechanistic_support': 4, 'background_mechanism': 1}
- Translational risks: {'no_direct_human_measure': 6, 'small_animal_model': 4, 'species_difference': 4}
- Animal evidence is used for mechanistic plausibility, not direct human clinical support.

## LLM-assisted Evidence Verification

- LLM enabled: False
- Provider: openai
- Model: gpt-4.1-mini
- LLM calls attempted: 0
- LLM calls succeeded: 0
- LLM calls failed: 0
- Rule-only evidence count: 15
- LLM-verified evidence count: 0
- LLM-revised evidence count: 0
- LLM split claim count: 0
- LLM excluded claim count: 0
- Excluded evidence log: /home/jwj/code/SleepAgent/outputs/grounding/excluded_evidence_log.jsonl
- Failure fallback used: False

## Evidence Extraction Benchmark

- Mode: rule_only
- Mechanism recall: 0.0
- Mechanism precision: 0.0
- Direction accuracy: 0.0
- Modality accuracy: 0.0
- Species accuracy: 0.0
- Evidence context accuracy: 0.0
- Downstream role accuracy: 0.0
- Paper coverage: 0.0
- Hallucinated evidence count: 0

## Scientific Loop Input Files

- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/grounding/evidence_table.csv`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/grounding/evidence_table.json`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/grounding/mechanism_graph_nodes.csv`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/grounding/mechanism_graph_edges.csv`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/grounding/mechanism_graph.json`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/grounding/evidence_to_variable_map.yaml`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/grounding/approved_variables_from_grounding.yaml`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/profiles/theoretical_profile.yaml`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/profiles/observed_profile.yaml`
- `/home/zyb/Agent_skills/jwj/SleepAgent/outputs/profiles/analysis_ready_profile.yaml`
