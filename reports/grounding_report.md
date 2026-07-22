# Knowledge Grounding Report

## Summary

- Literature records: 1
- Evidence records: 4
- Mechanism graph nodes: 29
- Mechanism graph edges: 43

## Grounding Corpus Build

- Corpus version: sleepagent_grounding_corpus_v1
- Query set version: 
- Build time: 2026-07-22T05:18:34.744926+00:00
- API enabled: True
- Providers: pubmed, europe_pmc, openalex, semantic_scholar
- Query count: 1
- API raw retrieved count: 1
- API deduplicated count: 1
- Final literature count: 1
- Evidence count: 4
- High-quality evidence count: 4
- Mechanism graph nodes: 29
- Mechanism graph edges: 43
- Mapped concepts: 0
- Ambiguous concepts: 3
- Unavailable concepts: 1
- Fallback used: False
- Output manifest: /home/zyb/Agent_skills/SleepAgent/outputs/grounding/corpus_manifest.json

## Evidence Direction Counts

- support: 4
- refute: 0
- null: 0
- unclear: 0

## Evidence Quality

- min: 0.830
- mean: 0.830
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

- `default mode network dysregulation` candidates=[]

## Ambiguous Mappings

- `slow-wave generation` approved=['slow_wave_density', 'delta_power']
- `thalamocortical coupling` approved=['thalamus_DMN_FC', 'thalamic_radiation_FA']
- `insomnia severity` approved=['ISI', 'PSQI']

## Main Confounds

- age
- medication
- sex

## API Literature Retrieval

- API enabled: True
- Providers used: mock_provider
- Search query count: 1
- Records retrieved per provider: {'mock_provider': 1}
- Provider-level results:
  - PubMed: 0
  - Europe PMC: 0
  - OpenAlex: 0
  - Semantic Scholar: 0
- API records before deduplication: 1
- API records after deduplication: 1
- Final literature count: 1
- API errors: none
- API warnings: none
- Cache enabled: False
- Cache hit count if available: unavailable
- Cache directory: 

## Data Grounding

- Analysis-ready features: 19
- Mapped variables: ['ISI', 'PSQI', 'delta_power', 'slow_wave_density', 'thalamic_radiation_FA', 'thalamus_DMN_FC']
- Unavailable theory-only concepts: ['default mode network dysregulation']
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
- Recommended next steps: Review query coverage or API availability before using this corpus for benchmark work.; Inspect extraction rules and online literature coverage.; Add targeted online queries for mechanisms listed in check_mechanism_coverage.gaps.; Review query set and extraction rules for null/refuting findings.

## Evidence Extraction Completeness

- Total papers: 1
- Papers with evidence: 1
- Papers without evidence: 0
- Evidence count: 4
- Evidence per paper: mean=4.0, median=4.0
- Direction counts: {'support': 4}
- Mechanism coverage: {'slow-wave generation': 1, 'thalamocortical coupling': 1, 'default mode network dysregulation': 1, 'insomnia severity': 1}
- Mechanisms with zero evidence: ['spindle generation', 'hyperarousal', 'white matter integrity', 'salience network dysregulation', 'limbic structural vulnerability']
- Missing variable rate: 0.0
- Missing modality rate: 0.0
- Unclear direction rate: 0.0
- Possible positive evidence bias: True
- Unmatched relevant papers: []

## Evidence Quality and Feasibility

- Mean extraction confidence score: 1.0
- Mean evidence quality score: 0.83
- Mean mechanistic strength score: 0.51
- Mean clinical applicability score: 1.0
- Mean evidence feasibility score: 0.97
- Mean final evidence score: 0.803
- High feasibility evidence count: 4
- High citation but low feasibility evidence: 0
- High mechanistic but low clinical applicability evidence: 0

## Citation and Journal Metadata

- Citation availability rate: 0.0
- Journal availability rate: 0.0
- Median citation count: 0.0
- Citation source breakdown: {'missing': 4}
- Journal metric availability: 0.0
- Note: citation and journal metrics are auxiliary and not primary evidence quality determinants.

## Animal and Translational Evidence

- Human evidence count: 4
- Animal evidence count: 0
- Translational evidence count: 0
- Species distribution: {'human': 4}
- Evidence context distribution: {'human_clinical': 4}
- Downstream role distribution: {'direct_human_evidence': 4}
- Translational risks: {}
- Animal evidence is used for mechanistic plausibility, not direct human clinical support.

## LLM-assisted Evidence Verification

- LLM enabled: False
- Provider: openai
- Model: gpt-4.1-mini
- LLM calls attempted: 0
- LLM calls succeeded: 0
- LLM calls failed: 0
- Rule-only evidence count: 4
- LLM-verified evidence count: 0
- LLM-revised evidence count: 0
- LLM split claim count: 0
- LLM excluded claim count: 0
- Excluded evidence log: /home/zyb/Agent_skills/SleepAgent/outputs/grounding/excluded_evidence_log.jsonl
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
