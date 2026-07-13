---
name: fmri-fmriprep-qc
description: 可执行 fMRIPrep/QC stage。用于运行或复用 fMRIPrep 输出，并整理每个 session 的 figures。
---

# fMRI fMRIPrep QC

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-fmriprep-qc/scripts/run_fmriprep_qc.py --subject sub-YZ1
```

该 stage 会先确保 BIDS 已准备好，再调用共享函数运行或复用 fMRIPrep，随后定位 BOLD、confounds 和 figures，并写入 `logs/stage_fmriprep_qc.json`。
