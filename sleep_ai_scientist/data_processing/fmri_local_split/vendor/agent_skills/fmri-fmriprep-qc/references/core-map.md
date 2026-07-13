# 代码映射

- `fMRIPrepFactory.config_environment()`：设置 CPU 和内存。
- `fMRIPrepFactory.config_execution()`：设置 BIDS、输出、FreeSurfer、work、task 参数。
- `fMRIPrepFactory.config_workflow()`：设置 BOLD 到 T1w、标准空间、ReconAll、SDC、Aroma 等 workflow 参数。
- `fMRIPrepFactory.config_run()`：写入 TOML 并调用 `fmriprep.cli.workflow.build_workflow()`。
