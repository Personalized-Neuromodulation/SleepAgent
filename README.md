# SleepAgent

SleepAgent is a vertical AI Scientist project for sleep science. The current implementation is a deterministic, local research loop that turns existing multimodal sleep data products and literature evidence into grounded hypotheses, locked computational experiment plans, critic reviews, and Co-Scientist-style research proposals.


## Run By Function

```bash
python -m sleep_ai_scientist.cli foundation build --config configs/foundation_config.yaml
python -m sleep_ai_scientist.cli grounding build --config configs/grounding_config.yaml
python -m sleep_ai_scientist.cli scientific-loop run --hypothesis-config configs/hypothesis_config.yaml --experiment-config configs/experiment_config.yaml
python -m sleep_ai_scientist.cli co-scientist run --config configs/co_scientist_config.yaml
```

Script equivalents:

```bash
python scripts/run_data_foundation.py --config configs/foundation_config.yaml
python scripts/run_grounding.py --config configs/grounding_config.yaml
python scripts/run_scientific_loop.py --hypothesis-config configs/hypothesis_config.yaml --experiment-config configs/experiment_config.yaml
python scripts/run_co_scientist.py --config configs/co_scientist_config.yaml
```

Main outputs:

- `data/foundation/subject_index.csv`
- `data/foundation/feature_registry.csv`
- `data/foundation/approved_variables.yaml`
- `data/foundation/data_dictionary.yaml`
- `data/foundation/qc_summary.csv`
- `data/foundation/multimodal_master_table.csv`
- `outputs/grounding/evidence_table.csv`
- `outputs/grounding/evidence_table.json`
- `outputs/grounding/mechanism_graph_nodes.csv`
- `outputs/grounding/mechanism_graph_edges.csv`
- `outputs/grounding/mechanism_graph.json`
- `outputs/grounding/evidence_to_variable_map.yaml`
- `outputs/grounding/approved_variables_from_grounding.yaml`
- `outputs/profiles/theoretical_profile.yaml`
- `outputs/profiles/observed_profile.yaml`
- `outputs/profiles/analysis_ready_profile.yaml`
- `outputs/hypotheses/top_k_hypotheses.json`
- `outputs/experiments/locked_plans/`
- `outputs/experiments/results/`
- `outputs/experiments/critic_reviews/`
- `outputs/co_scientist/co_scientist_top_k.json`
- `reports/data_foundation_report.md`
- `reports/grounding_report.md`
- `reports/scientific_loop_report.md`
- `reports/co_scientist_report.md`
