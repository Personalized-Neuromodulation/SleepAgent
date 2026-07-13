# 代码映射

- `fMRITarget.find_region()`：根据 HCP cortex、半球、cfdrp 阈值和排序规则筛选区域。
- `fMRITarget.default_region_xyz()`：统计不可用时使用默认刺激区域。
- `REGION_DEFAULT_CONFIG`：定义默认 cortex、hemisphere 和 HCP region。
- `fMRIPath.get_stim_target()`：定位 PALM cfdrp、HCP label 和 SIMNIBS 输出目录。
