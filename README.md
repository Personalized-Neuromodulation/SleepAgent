# SleepAgent

SleepAgent is a vertical AI Scientist project for sleep science. Phase 1 implements a Knowledge & Data Grounding System that turns seed literature and Data Foundation products into structured evidence, mechanism graphs, variable mappings, and analysis-ready data profiles.

Phase 1 deliberately does not implement hypothesis generation, experiment execution, online API calls, Co-Scientist tournaments, or RL. It reads Data Foundation outputs and falls back to toy fixtures when foundation files are unavailable.

## Run Phase 1

```bash
python -m sleep_ai_scientist.cli grounding build --config configs/grounding_config.yaml
```

or:

```bash
python scripts/run_phase1_grounding.py --config configs/grounding_config.yaml
```

Main outputs:

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
- `reports/phase1_grounding_report.md`
