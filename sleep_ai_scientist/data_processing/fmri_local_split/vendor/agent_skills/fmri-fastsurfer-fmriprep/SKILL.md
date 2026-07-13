---
name: fmri-fastsurfer-fmriprep
description: FastSurfer 支持脚本。由 local agent 在 --surface-mode 1 时先运行，再让 fMRIPrep 复用 FastSurfer subjects_dir。
---

# fMRI FastSurfer

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-fastsurfer-fmriprep/scripts/run_fastsurfer_fmriprep.py --help
```

在 split agent 中，FastSurfer 不作为用户编排列表里的独立 stage；选择 `--surface-mode 1` 或任务中提到 `fastsurfer` 时，agent 会在需要 fMRIPrep/surface 的阶段前准备 FastSurfer 输出。
