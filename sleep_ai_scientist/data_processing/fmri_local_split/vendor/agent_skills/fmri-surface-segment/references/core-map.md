# 代码映射

- `fMRISpatialTransform.bold_2_surf()`：使用 fMRIPrep `init_bold_surf_wf` 做表面采样。
- `fMRISpatialTransform.surf_mask()`：从 func.gii 生成有效顶点 mask。
- `fMRIPath.get_resample_data()`：从 workflow 目录提取 lh/rh 表面结果到 `clean_data/surface`。
- `fMRIPath.get_segment_path()`：组织切分输入和输出目录。
