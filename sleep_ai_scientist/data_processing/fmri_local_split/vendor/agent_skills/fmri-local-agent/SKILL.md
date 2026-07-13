---
name: fmri-local-agent
description: 根据用户输入编排本地 fMRI 可执行 skills。完整分析或未说明局部任务时默认执行全流程；明确提出局部任务时只执行对应阶段。
---

# fMRI Local Split Agent

## 入口

```bash
python /home/zyb/Agent_skills/fmri_local_split/fmri_local_agent.py --help
```

## 编排规则

- 完整流程：BIDS、fMRIPrep/QC、去噪、分段、时频/QC。
- 局部任务：根据关键词只运行对应 stage，例如 `去噪`、`segment`、`sleep_label`、`ALFF/fALFF`、`fMRIPrep`。
- FastSurfer 由 `--surface-mode 1` 或任务中提到 `fastsurfer` 触发，不作为独立 stage。
- 本地 LLM 不可用时，仍使用关键词规则执行，不阻断任务。

## 示例

```bash
python /home/zyb/Agent_skills/fmri_local_split/fmri_local_agent.py --surface-mode 0 "完整分析fmri数据 sub-YZ1"
python /home/zyb/Agent_skills/fmri_local_split/fmri_local_agent.py --surface-mode 0 "只对sub-YZ1执行segment分段"
python /home/zyb/Agent_skills/fmri_local_split/fmri_local_agent.py --surface-mode 1 "只对sub-YZ1执行fMRIPrep和去噪"
```
