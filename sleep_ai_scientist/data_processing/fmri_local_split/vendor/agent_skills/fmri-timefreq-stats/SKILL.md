---
name: fmri-timefreq-stats
description: 可执行时频和 QC stage。用于基于 clean/segment 数据计算 ALFF/fALFF、PSD 和统计摘要。
---

# fMRI Time Frequency Stats

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-timefreq-stats/scripts/run_timefreq_stats.py --subject sub-YZ1
```

该 stage 读取 clean BOLD 输出，执行 time_frequency 和 qc_statistics，并写入 `logs/stage_timefreq_stats.json`。
