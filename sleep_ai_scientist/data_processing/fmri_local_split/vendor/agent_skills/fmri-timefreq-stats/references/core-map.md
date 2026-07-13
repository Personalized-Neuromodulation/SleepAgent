# 代码映射

- `fMRI.read_clean_data()`：读取 volume NIfTI 或 surface MAT，并根据 bad epochs 过滤时间点。
- `fMRITFFactory.create_individual_band_power()`：计算 ALFF/fALFF 并写 JSON。
- `BandPower.band_power()`：滤波并计算频段能量。
- `RestfMRI.format_data_design_contrast_matrix()`：生成 PALM 需要的数据、设计和对比矩阵。
