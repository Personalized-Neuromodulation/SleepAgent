# Multi-Agent Structure

本目录实现五个本地 agent，不依赖 Edison 平台。所有 agent 对外命名统一使用 snake_case：`planner_agent`、`scientist_agent`、`coder_agent`、`reviewer_agent`、`analyst_agent`。每个 agent 目录包含该 agent 的主要工程实现；顶层 workflow 只负责编排和记录，不直接承载 agent 的业务逻辑。

## planner_agent

负责数据准备、fMRI 预处理门控、数据清单扫描和候选实验路线规划。

主要实现：

- `planner/fmri_preprocessing.py`
- `planner/data_inventory.py`
- `planner/fmri_inventory.py`
- `planner/paradigms.py`（内部兼容命名；对外作为 analysis route 使用）

## scientist_agent

负责文献检索/筛选、创新点 idea 生成、自我反思和 pairwise tournament 排序。

主要实现：

- `scientist/literature.py`
- `scientist/innovation.py`

## coder_agent

负责检索参考代码资源，并为每个创新点绑定的实验路线生成可执行 Python 实验代码。

主要实现：

- `coder/code_search.py`
- `coder/code_generation.py`

## reviewer_agent

负责实验路线评分、创新点评分和执行质量审阅。

主要实现：

- `reviewer/scoring.py`

## analyst_agent

负责执行实验、读取 result.json、汇总图表，并执行 Robin 式本地反馈。

主要实现：

- `analyst/execution.py`
- `analyst/visualization.py`
- `analyst/stage_network_topomap.py`
- `analyst/robin_feedback.py`

反馈步骤：

1. 解释实验结果。
2. 提取机制洞察和未被当前数据检验的部分。
3. 根据真实指标反向修正假设和创新点。
4. 提出下一步实验。

该反馈机制参考 Robin 论文的闭环思想，但本实现完全在本地运行，不调用 Edison 平台。
