---
name: fmri-bids-ingest
description: 可执行 BIDS 导入 stage。用于把当前 subject 的 DICOM/NIfTI 输入整理到 fMRIPrep 可用的 BIDS 数据集。
---

# fMRI BIDS Ingest

## 执行

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-bids-ingest/scripts/run_bids_ingest.py --subject sub-YZ1
```

也可通过 dispatcher：

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py bids
```

该 stage 复用 `run_layered_skill_analysis.py` 中的 BIDS 准备函数，并写入 `logs/stage_bids_ingest.json`。
