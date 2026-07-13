---
name: fmri-pipeline
description: fMRI split pipeline dispatcher。用于按命令调用独立可执行 stage，而不是直接运行单一端到端脚本。
---

# fMRI Split Pipeline

## 命令

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py full
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py bids
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py fmriprep
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py denoise
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py segment
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py timefreq
```

`analyze` 是 `full` 的兼容别名。每个命令都会调用对应 `agent_skills/<stage>/scripts/run_*.py`。

## Stage

- `bids`: `fmri-bids-ingest/scripts/run_bids_ingest.py`
- `fmriprep`: `fmri-fmriprep-qc/scripts/run_fmriprep_qc.py`
- `denoise`: `fmri-denoise-regressors/scripts/run_denoise_regressors.py`
- `segment`: `fmri-surface-segment/scripts/run_surface_segment.py`
- `timefreq`: `fmri-timefreq-stats/scripts/run_timefreq_stats.py`
