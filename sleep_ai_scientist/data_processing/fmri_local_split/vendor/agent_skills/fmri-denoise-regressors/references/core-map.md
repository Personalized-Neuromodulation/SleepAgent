# 代码映射

- `fMRIRegressorFactory.motion_regressor()`：从 confounds TSV 提取 12 个头动参数。
- `fMRIRegressorFactory.csf_wm_regressor()`：按累计解释方差选择 c/w CompCor。
- `fMRIRegressorFactory.combine_all_regressor()`：拼接多个 `score` 矩阵。
- `fMRIDenoiseFactory.denoise()`：调用 MATLAB `nuisance_regressout_volume.m`。
- `fMRIOutliersFactory.outliers()`：调用 `fsl_motion_outliers` 生成 FD/DVARS。
