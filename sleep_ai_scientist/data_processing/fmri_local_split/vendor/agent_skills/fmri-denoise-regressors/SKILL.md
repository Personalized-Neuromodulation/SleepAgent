---
name: fmri-denoise-regressors
description: 可执行去噪 stage。用于基于 fMRIPrep confounds 生成回归器、去噪 BOLD/surface，并生成去噪后的 carpetplot。
---

# fMRI Denoise Regressors

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-denoise-regressors/scripts/run_denoise_regressors.py --subject sub-YZ1
```

该 stage 读取 fMRIPrep BOLD 和 confounds，生成 motion/CSF/WM 等回归器，输出 `clean_*` 目录和 `qc_statistics/*desc-carpetplot_bold.svg`，并写入 `logs/stage_denoise_regressors.json`。
