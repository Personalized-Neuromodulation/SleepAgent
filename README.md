# Neuroscience Research Agent

`neuroscience_research_agent` is a standalone research-agent project placed next to the fMRI projects under `/home/qlp/Agent_skills`.

It is inspired by `AI-Researcher` and Robin, but the active system is implemented as local agents under `neuro_research_agent/agents`: `planner_agent`, `scientist_agent`, `coder_agent`, `reviewer_agent`, and `analyst_agent`. This agent targets general neuroscience research workflows rather than only fMRI:

```text
用户研究问题
  -> 多轮文献/代码/数据检索
  -> gap / trend / claim 提取
  -> idea 候选生成
  -> idea 自反思与排序
  -> 数据可行性检查
  -> 自动生成实验计划
  -> 代码生成/调用已有工具
  -> 运行实验
  -> 结果反馈
  -> 下一轮 idea 修正
```

Idea generation is now KG-aware: `scientist_agent` combines retrieved papers, optional NeuroClaw/NeuroOracle knowledge-graph evidence, and `planner_agent` local-data feasibility checks before ranking ideas. If a NeuroOracle snapshot or hypothesis JSON is available, the agent uses matched claims, hypotheses, region terms, ROI hints, and evidence scores. If no KG snapshot is present, it falls back to a lightweight KG-style evidence bundle derived from retrieved literature plus local data feasibility, so the workflow remains executable.

The literature stage requires online retrieval. If online paper search returns no usable candidates, the run stops.

Interactive runs use the local Ollama service to parse each user task into structured fields before confirmation. The prompt can include an absolute data path such as `/path/to/data`; current fMRI workflows treat that path as an already processed fMRI output directory. Defaults are 20 papers, 10 code search results, and live search enabled. Subject and session are not inferred from the prompt by default. Enter `yes` to continue, or `no` to return to task input. For non-interactive runs, pass `--yes`.

Ollama parsing uses `http://localhost:11434` by default and automatically selects the first installed model. Override with `--ollama-url`, `--ollama-model`, or environment variables `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

## Quick Start

```bash
/home/qlp/anaconda3/envs/agent/bin/python \
  /home/qlp/Agent_skills/neuroscience_research_agent/scripts/run_neuroscience_research_agent.py \
  --prompt "研究睡眠状态下丘脑皮层通信和脑网络变化" \
  --data-root /media/qlp/68ACC1E8ACC1B13C/fmri_agent/test_data/output/analysis_free \
  --yes
```

For non-fMRI neuroscience data, pass only `--data-root`:

```bash
/home/qlp/anaconda3/envs/agent/bin/python \
  /home/qlp/Agent_skills/neuroscience_research_agent/scripts/run_neuroscience_research_agent.py \
  --prompt "分析 EEG alpha/theta 振荡与行为反应时的关系，并提出可验证创新点" \
  --data-root /path/to/neuroscience_dataset \
  --yes
```

Outputs are written to:

```text
neuroscience_research_agent/outputs/<run_id>/
  papers/
  papers/retrieved_papers.md
  experiments/<innovation_id>/*.py
  experiments/<innovation_id>/literature_context.md
  experiments/<innovation_id>/experiment_plan.md
  experiments/<innovation_id>/execution_manifest.md
  innovation/innovation_points.md
  innovation/innovation_generation_process.md
  innovation/innovation_generation_process_with_feedback.md
  innovation/innovation_scores.json
  innovation/innovation_scores.md
  data/data_inventory.md
  knowledge_graph/kg_context.md
  paradigms/candidate_analysis_routes.md
  paradigms/analysis_route_scores.md
  paradigms/analysis_route_details.md
  execution/<analysis_route>/result.json
  execution/<functional_connectivity_route>/*_connectome_3d.html
  figures/paradigm_scores.svg               # internal file name kept for compatibility
  figures/paradigm_score_heatmap.svg        # internal file name kept for compatibility
  figures/figures.md
  steps/
  steps/<step_index>_<step_name>.md
  steps/manifest.md
  final_report.md
  run_status.md
```

Machine-readable JSON files are still written for runtime compatibility, generated-code execution, and configuration-style manifests. User-facing reports, KG evidence, step processes, scores, inventories, and experiment plans are mirrored as Markdown.

Each generated experiment writes its own result JSON and any matrices/CSV summaries it creates. Functional-connectivity routes also save ROI coordinates and a Nilearn `view_connectome` 3D HTML plot when Nilearn is available. Experiments that cannot be reproduced with the supplied data still produce a `result.json` with `status: not_executable` and an explicit missing-data reason.

## Supported Data Families

- fMRI/BIDS outputs: cleaned BOLD, surface BOLD, events, time-frequency outputs, sleep segmentation.
- EEG/MEG: EDF/BDF/SET/FIF plus event files.
- Electrophysiology: spike/unit tables, spike NPY arrays, LFP arrays/tables.
- Behavior and cognition: trial tables, reaction time, accuracy, labels, phenotypes.
- Eye tracking and physiology: gaze, pupil, fixation/saccade, ECG/respiration/physio files.
- Structural and molecular data: T1/T2 MRI, DWI, PET, calcium imaging, transcriptomics/single-cell/omics.
- Multimodal studies: mixed folders with labels or phenotype tables.

## Stage Network Topomap

Stage-wise ROI connectivity edges can be visualized as scalp top-view network maps. The implementation lives in `neuro_research_agent/agents/analyst_agent/stage_network_topomap.py` and should be called by workflow or `analyst_agent` code, not as a separate script entrypoint:

```python
from pathlib import Path

from neuro_research_agent.agents.analyst_agent.stage_network_topomap import plot_stage_network_topomaps

plot_stage_network_topomaps(
    edges_csv=Path("/path/to/stage_network_fc_edges.csv"),
    out_dir=Path("/path/to/topomap_figures"),
    top_n=30,
    min_abs_r=0.25,
)
```

The plot is a topographic network projection for fMRI ROI connectivity, not an EEG electrode interpolation map. Red edges are positive FC, blue edges are negative FC, and edge width reflects FC strength.
