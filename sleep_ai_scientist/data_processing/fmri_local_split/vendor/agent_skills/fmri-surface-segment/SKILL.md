---
name: fmri-surface-segment
description: 可执行 surface/segment stage。用于整理 surface transform，并在存在 sleep_label.csv 时按睡眠分期切分 clean 数据。
---

# fMRI Surface Segment

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-surface-segment/scripts/run_surface_segment.py --subject sub-YZ1
```

该 stage 使用已经去噪的 clean BOLD/surface 文件。若输入 session 下没有 `sleep_label.csv`，该 session 不执行 segment；若存在，则按核心分段逻辑输出 `segment`，并写入 `logs/stage_surface_segment.json`。
