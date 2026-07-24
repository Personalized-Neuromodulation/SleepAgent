# SleepAgent 中文工程说明

SleepAgent 是一个面向睡眠科学的垂直科学发现系统。工程目标不是只生成单次报告，而是把数据基础、文献库、RAG grounding、知识图谱、假说生成、实验建模、结果反馈、文献检索意图和下一轮迭代连接成一个可追溯的闭环。

当前主线流程可以概括为：

```text
原始/派生数据
  -> foundation 数据基础
  -> literature 文献库与 RAG 索引
  -> grounding 证据抽取、变量映射、机制图谱、analysis-ready profile
  -> hypothesis 假说生成、评审、排序、当前数据可检验性标注
  -> experiment 实验计划、特征抽取、统计建模、ML 建模、稳健性、负控、可视化
  -> experimental feedback
  -> 文献检索意图
  -> 新 query 扩充原 query 列表
  -> 新文献 / 新 grounding / 新假说
```

## 目录结构

```text
configs/                  配置文件
data/foundation/          foundation 生成的数据资产、变量注册表、主表
data/literature/          文献 SQLite DB 和文献 registry
outputs/grounding/        grounding 证据、知识图谱、变量映射、LLM context
outputs/hypotheses/       单独运行 hypothesis 阶段时的默认输出
outputs/experiments/      单独运行 experiment 阶段时的默认输出
outputs/discovery_loop/   discovery loop 每轮的完整本地输出
outputs/features/         单独运行 experiment/feature 阶段时的默认特征输出
reports/                  phase0-phase4 Markdown 报告
scripts/                  常用端到端脚本
sleep_ai_scientist/       Python 源码
tests/                    测试
```

## 安装与环境

Python 版本要求：

```text
Python >= 3.10
```

主要依赖在 `pyproject.toml` 中，包括：

```text
pydantic, pyyaml, sqlalchemy, requests, sentence-transformers,
scikit-learn, statsmodels, matplotlib, xgboost, lightgbm
```

推荐安装：

```bash
pip install -e .
```

如果要运行测试依赖：

```bash
pip install -e ".[test]"
```

在线文献 API 运行前需要至少设置 `NCBI_EMAIL`：

```bash
export NCBI_EMAIL=your_email@example.com
export NCBI_TOOL=SleepAgent
```

可选 API key：

```bash
export NCBI_API_KEY=...
export SEMANTIC_SCHOLAR_API_KEY=...
export OPENALEX_API_KEY=...
```

默认本地 SQLite 路径：

```bash
export SLEEPAGENT_SQLITE_PATH=/home/zyb/Agent_skills/SleepAgent/data/literature/sleep_literature.db
```

## 常用运行命令

初始化或检查数据库：

```bash
python -m sleep_ai_scientist.cli db init --config configs/database_config.yaml --backend sqlite
python -m sleep_ai_scientist.cli db healthcheck --config configs/database_config.yaml --backend sqlite
```

构建 foundation：

```bash
python -m sleep_ai_scientist.cli foundation build --config configs/foundation_config.yaml
```

构建知识源 registry：

```bash
python -m sleep_ai_scientist.cli knowledge build --config configs/knowledge_sources_config.yaml --backend sqlite
```

构建文献库：

```bash
python -m sleep_ai_scientist.cli literature build \
  --config configs/literature_library_config.yaml \
  --query-config configs/literature_queries.yaml \
  --library-version sleep_literature_library_v1 \
  --backend sqlite \
  --enable-api \
  --enable-rag-index
```

运行 grounding：

```bash
python -m sleep_ai_scientist.cli grounding build --config configs/grounding_config.yaml
```

运行 foundation + online literature + grounding：

```bash
bash scripts/run_foundation_grounding_online.sh
```

运行 discovery loop：

```bash
bash scripts/run_discovery_loop.sh configs/discovery_loop_config.yaml 2
```

运行端到端流程：

```bash
bash scripts/run_all_tests.sh 2
```

运行测试：

```bash
python -m pytest
```

默认 pytest 会跳过 `postgres_live`、`api_live`、`llm_live` 标记的测试。

## 配置文件总览

核心配置：

```text
configs/foundation_config.yaml          数据基础层
configs/literature_library_config.yaml  文献库、API、RAG、embedding
configs/literature_queries.yaml         文献查询列表
configs/grounding_config.yaml           grounding、top-K、证据抽取、profile
configs/hypothesis_config.yaml          假说生成、评审、排序
configs/experiment_config.yaml          实验设计、模型选择、可视化
configs/discovery_loop_config.yaml      迭代闭环
configs/database_config.yaml            数据库后端
configs/llm_config.yaml                 LLM provider 和开关
```

工程中大部分路径都通过配置控制。`configs/discovery_loop_config.yaml` 会把 hypothesis、experiment、foundation、literature、grounding 串起来。

## Phase 0: Foundation 数据基础

入口：

```text
sleep_ai_scientist/foundation/foundation_pipeline.py
```

主要作用：

```text
1. 读取 subject table、EEG/fMRI/DTI/MRI/scales 特征表和 QC 表。
2. 统一 subject_id、group、modality、feature_name 等字段。
3. 生成 subject_index、feature_registry、approved_variables、data_dictionary。
4. 根据缺失率、样本量、QC 状态标注变量是否 approved。
5. 合并 multimodal_master_table。
6. 记录 data_asset_registry 和 update_history。
```

主要输出：

```text
data/foundation/subject_index.csv
data/foundation/feature_registry.csv
data/foundation/approved_variables.yaml
data/foundation/data_dictionary.yaml
data/foundation/qc_summary.csv
data/foundation/multimodal_master_table.csv
data/foundation/foundation_manifest.json
data/foundation/data_asset_registry.jsonl
data/foundation/foundation_update_history.jsonl
reports/phase0_foundation_report.md
```

Foundation features 的作用：

```text
1. 告诉系统当前有哪些真实可用变量。
2. 给 grounding 的 observed_profile / analysis_ready_profile 提供数据约束。
3. 给 hypothesis 阶段提供当前数据可检验性标注。
4. 给 experiment 阶段提供可建模变量和缺失率信息。
5. 在 discovery loop 中，如果实验产生新特征表，foundation 会更新资产和变量注册表。
```

需要注意：foundation feature 本身不会直接生成文献。文献扩增应由实验结果产生的“科学问题/证据缺口/负控失败/缺失变量/模态缺口”驱动。

## Literature 文献库与 RAG

入口：

```text
sleep_ai_scientist/literature/library_builder.py
sleep_ai_scientist/api/literature_client.py
sleep_ai_scientist/literature/rag_indexer.py
sleep_ai_scientist/literature/rag_retriever.py
```

文献源：

```text
PubMed
Europe PMC
OpenAlex
Semantic Scholar
```

构建过程：

```text
1. 读取 configs/literature_queries.yaml 中的 query。
2. 调用已启用的 API provider。
3. 统一字段、规范化 DOI/PMID/PMCID/title。
4. 写出 API 检索 CSV。
5. 持久化到 SQLite/PostgreSQL。
6. 按 DOI、PMID、PMCID、normalized title 去重。
7. 导出 literature registry。
8. 生成 provider/query summary、coverage audit、anchor papers。
9. 生成 query expansion candidates。
10. 构建 RAG chunks 和 embedding。
11. 写 manifest 和 build report。
```

主要输出：

```text
data/literature/sleep_literature.db
data/literature/sleep_literature_registry.csv
outputs/literature/sleep_library_api_retrieved_papers.csv
outputs/literature/literature_deduplication_report.csv
outputs/literature/provider_summary.json
outputs/literature/query_summary.csv
outputs/literature/query_coverage_audit.csv
outputs/literature/coverage_audit.json
outputs/literature/anchor_papers.csv
outputs/literature/query_expansion_candidates.csv
outputs/literature/sleep_library_manifest.json
outputs/literature/sleep_library_build_report.md
```

RAG embedding 默认配置：

```text
provider: local_minilm
model: sentence-transformers/all-MiniLM-L6-v2
dim: 384
local_files_only: true
```

文献库扩增原则：

```text
后续迭代不应该固定重复检索原始 query。
实验结果先生成文献检索意图。
只有当意图产生新 query 时，才扩充文献库。
新 query 会追加到 configs/literature_queries.yaml 的 experiment_feedback_expansion 分组。
当前迭代也会写出 outputs/discovery_loop/iteration_xxx/literature_incremental_queries.yaml。
```

## Phase 1: Grounding

入口：

```text
sleep_ai_scientist/grounding/grounding_pipeline.py
```

Grounding 的作用是把文献和 foundation 数据约束转化为假说生成可用的结构化上下文：

```text
文献 / RAG top-K
  -> evidence extraction
  -> evidence grading
  -> theoretical profile
  -> observed profile
  -> analysis_ready_profile
  -> evidence_to_variable_map
  -> mechanism_graph
  -> LLM context compression
```

主要输出：

```text
outputs/grounding/evidence_table.csv
outputs/grounding/evidence_table.json
outputs/grounding/evidence_quality_summary.json
outputs/grounding/evidence_extraction_audit.json
outputs/grounding/evidence_to_variable_map.yaml
outputs/grounding/approved_variables_from_grounding.yaml
outputs/grounding/mechanism_graph_nodes.csv
outputs/grounding/mechanism_graph_edges.csv
outputs/grounding/mechanism_graph.json
outputs/grounding/llm_evidence_context.json
outputs/grounding/llm_mechanism_context.json
outputs/grounding/grounding_qc_report.json
outputs/grounding/corpus_manifest.json
outputs/profiles/theoretical_profile.yaml
outputs/profiles/observed_profile.yaml
outputs/profiles/analysis_ready_profile.yaml
reports/phase1_grounding_report.md
```

### Grounding top-K 原则

`configs/grounding_config.yaml` 中默认配置：

```yaml
retrieval:
  source: literature_db_rag
  query: sleep insomnia thalamocortical slow wave spindle
  top_k: 1000
```

在普通 grounding build 中，如果没有动态 query，会使用配置里的 `retrieval.query`。

在 discovery loop 中，grounding top-K query 会动态生成，来源包括：

```text
hypothesis.research_question
experiment-driven literature intent queries
evidence gap / failed mechanism terms
DataFeature / approved variable names
```

代码会打印日志：

```text
[grounding_topk_query] sources={...}
[grounding_topk_query] query=...
```

这样可以追踪 top-K 到底用了哪些 query 来源。

## Phase 2: Hypothesis 假说生成与排序

入口：

```text
sleep_ai_scientist/hypothesis/hypothesis_pipeline.py
sleep_ai_scientist/hypothesis/supervisor.py
```

假说阶段读取：

```text
outputs/grounding/llm_evidence_context.json
outputs/grounding/llm_mechanism_context.json
outputs/grounding/evidence_table.json
outputs/grounding/mechanism_graph.json
outputs/profiles/analysis_ready_profile.yaml
outputs/hypotheses/experimental_feedback.json
outputs/memory/reward_memory.json
```

当前假说生命周期由 5 个组件完成：

```text
ContextAgent              构造证据、机制图、历史反馈上下文
GenerationAgent           生成候选假说
ReviewAgent               评审新颖性、证据支持、可测试性、重复度
RankAgent                 tournament / Elo 排序
EvolutionMemoryAgent      写出结果，吸收实验反馈，演化假说
```

单独运行 hypothesis 阶段时的主要输出：

```text
outputs/hypotheses/context_blocks.json
outputs/hypotheses/hypothesis_pool.json
outputs/hypotheses/hypothesis_registry.csv
outputs/hypotheses/hypothesis_reviews.json
outputs/hypotheses/tournament_matches.json
outputs/hypotheses/top_k_hypotheses.json
outputs/hypotheses/hypothesis_lineage.json
reports/phase2_hypothesis_report.md
```

### 当前数据可检验性

入口：

```text
sleep_ai_scientist/hypothesis/testability.py
```

假说排序前会根据当前 `analysis_ready_profile` 标注：

```text
directly_testable
partially_testable
not_directly_testable
unknown
```

判断依据包括：

```text
1. 假说文本中暗示的模态：fMRI、EEG、DTI、MRI、scales。
2. 假说文本中暗示的变量：FA、DMN_FC、thalamus_DMN_FC、spindle_density、ISI 等。
3. 当前 analysis-ready profile 中是否真的有这些变量。
4. 是否只有 proxy，还是直接变量可用。
```

排序时会加入 `ranking_bonus`：

```text
directly_testable: +40
partially_testable: +10
not_directly_testable: -30
unknown: 0
```

这可以避免在 fMRI-only 数据下把 DTI/FA/EEG/spindle 假说误报为“当前数据已验证”。

## Phase 3: Experiment 实验建模

入口：

```text
sleep_ai_scientist/experiment/experiment_pipeline.py
sleep_ai_scientist/experiment/model_selection.py
sleep_ai_scientist/experiment/visualization.py
```

单独运行 experiment 阶段时读取：

```text
outputs/hypotheses/hypothesis_pool.json
outputs/profiles/analysis_ready_profile.yaml
outputs/grounding/approved_variables_from_grounding.yaml
outputs/grounding/evidence_to_variable_map.yaml
```

实验流程：

```text
1. ExperimentDesignAgent 从 top hypothesis 生成实验计划。
2. 可选 data_processing 处理原始 fMRI 数据。
3. FeatureExtraction 按实验计划抽取 fMRI/EEG/scales/DTI/MRI 特征。
4. TestabilityPrecheck 检查计划和当前 profile 是否匹配。
5. VariableMappingAgent 把假说变量映射到真实 feature。
6. StatisticalModelAgent 选择主模型、稳健性检验、负控检验、ML 模型。
7. ResultReviewAgent 生成支持度、critic findings、反馈。
8. visualization.py 生成每轮可追溯图像和 HTML dashboard。
9. feedback_builder 生成 experimental_feedback 给下一轮 hypothesis 使用。
```

单独运行 experiment 阶段时的主要输出：

```text
outputs/experiments/experiment_results.json
outputs/hypotheses/experimental_feedback.json
outputs/experiments/visuals/index.html
outputs/experiments/visuals/visualization_manifest.json
outputs/experiments/visuals/figures/*.png
outputs/features/profile/<plan_id>/analysis_ready_profile.yaml
outputs/features/fmri/<plan_id>/fmri_features.csv
outputs/features/multimodal/<plan_id>/multimodal_features.csv
reports/phase3_experiment_report.md
```

### predictors 和 outcome

`plan.predictors` 是用来解释或预测结果变量的输入变量。

`outcome` 是被解释或被预测的结果变量。

例如：

```text
predictors:
  thalamus_DMN_FC
  thalamus_salience_FC
  thalamus_frontoparietal_FC
  DMN_FC

outcome:
  salience_FC
```

含义是：使用若干网络连接强度或网络内部强度，去解释或预测 salience network functional connectivity。

### 模型选择策略

当前不使用 `enable_ml` 开关。系统会在所有配置的模型中按数据类型和实验范式自动选择。

主统计模型选择规则：

```text
二分类 outcome
  -> logistic_regression

存在 site/scanner/session/subject/group/batch/cohort 等分组结构
  -> mixed_effects

存在 covariates，尤其 mean_FD、mean_DVARS、max_FD、percent_high_motion
  -> linear_regression

没有二分类、没有分组、没有协变量
  -> spearman_correlation
```

ML 是否运行由策略自动判断：

```text
二分类 outcome
  -> 运行分类模型

连续 outcome 且 predictor 数量 >= 2
  -> 运行回归模型

样本量太小或变量不足
  -> 不运行 ML
```

候选 ML 模型：

```text
classification:
  logistic_regression
  decision_tree_classifier
  random_forest_classifier
  svm_classifier
  xgboost_classifier
  lightgbm_classifier

regression:
  decision_tree_regressor
  random_forest_regressor
  svm_regressor
  xgboost_regressor
  lightgbm_regressor
```

模型选择日志写入 `experiment_results.json` 的：

```text
metadata.model_trace.model_selection_policy
metadata.model_trace.controlled_templates
```

### 主统计检验、稳健性检验、负控检验

主统计检验：

```text
用于回答实验计划中的核心 predictor -> outcome 是否成立。
例如 linear_regression 中 effect 是回归系数，p_value 判断显著性。
```

稳健性检验：

```text
用于检查主结果在重采样或替代方法下方向是否稳定。
当前常见方法是 bootstrap_spearman_ci。
sign_stability 表示 bootstrap 中方向一致的比例。
```

负控检验：

```text
用于检查 predictor 是否也能强烈关联到理论上不应关联的 control outcome。
如果负控失败，说明主结果可能受到 global signal、motion、QC 或非特异因素影响。
```

### effect、p_value、R2

`effect` 表示效应大小和方向。

在线性回归中：

```text
effect = predictor 的回归系数
```

含义：

```text
effect > 0: predictor 越高，outcome 越高
effect < 0: predictor 越高，outcome 越低
```

`p_value` 判断该 effect 是否达到统计显著性。

`R2` 表示模型能解释 outcome 变异的比例，主要用于整体模型解释度或 ML 预测性能。R2 高不等于机制被证明，R2 低也不等于没有任何统计关联。

### 特征重要性

不同模型的特征重要性来源不同：

```text
DecisionTree / RandomForest / XGBoost / LightGBM:
  使用模型自身的 feature_importances_

线性模型:
  可使用系数或标准化系数

SVR RBF:
  没有 feature_importances_，也没有线性 coef_，因此当前记为 0
```

注意：不同模型的 feature_importances_ 尺度不一定一致，跨模型平均时应主要看排序趋势，不应当成可直接比较的机制效应。

### 可视化

每轮实验都会保存可追溯可视化结果。Discovery loop 内部不会从全局 `outputs/experiments` 复制图像，而是让本轮 experiment 直接写到 `outputs/discovery_loop/iteration_xxx/experiment/visuals`。

常见图：

```text
primary_test_matrix.png
linear_regression_fit_*.png
spearman_scatter_*.png
robustness_bootstrap_<plan_id>.png
negative_controls_<plan_id>.png
missingness_<plan_id>.png
ml_feature_importance_<plan_id>.png
ml_regression_predicted_observed_<plan_id>.png
ml_classification_*.png
```

manifest：

```text
outputs/experiments/visuals/visualization_manifest.json                      # 单独运行 experiment 时
outputs/discovery_loop/iteration_xxx/experiment/visuals/visualization_manifest.json
```

解释原则：

```text
primary_test_matrix:
  看哪些 predictor/outcome 组合显著，以及 effect 方向。

robustness_bootstrap:
  看方向稳定性，不等同于显著性。

negative_controls:
  红色/failed 表示负控失败，是混杂风险，不是强支持。

missingness:
  看变量缺失率和实际可用样本量。

ml_regression_predicted_observed:
  看预测值和真实值是否接近，反映预测能力，不直接证明机制。
```

## Phase 4: Discovery Loop

入口：

```text
sleep_ai_scientist/discovery_loop/discovery_runner.py
scripts/run_discovery_loop.sh
scripts/run_all_tests.sh
```

默认配置：

```yaml
discovery_loop:
  run_id: sleep_discovery_loop
  max_iterations: 2
  verbose: true
  snapshot_features: true
  enable_foundation_grounding_refresh: true
  stop_conditions:
    no_active_hypotheses: true
    no_experimental_feedback: false
    reward_convergence:
      enabled: true
      min_iterations: 2
      delta: 0.03
```

每轮顺序：

```text
1. hypothesis start
2. experiment start
3. foundation update from experiment feature tables
4. literature intent from experiment results
5. literature refresh only if new accepted query exists
6. grounding refresh
7. metrics collection
8. snapshot iteration outputs
9. stop condition check
```

每轮本地输出目录：

```text
outputs/discovery_loop/iteration_001/
outputs/discovery_loop/iteration_002/
...
```

每轮输出包括：

```text
loop_summary.json
hypothesis/
experiment/
experiment/visuals/
features/
foundation_update_config.yaml
literature_expansion_plan.json
literature_incremental_queries.yaml
```

Discovery loop 不再把 `outputs/hypotheses`、`outputs/experiments`、`outputs/features` 复制到 iteration 目录。每轮会临时生成本轮专用配置：

```text
iteration_xxx/hypothesis_config.yaml
iteration_xxx/experiment_config.yaml
```

然后各阶段直接写入：

```text
iteration_xxx/hypothesis/
iteration_xxx/experiment/
iteration_xxx/features/
```

因此 `iteration_002/features` 不应包含 `iteration_001` 的 plan 特征。

全局状态：

```text
outputs/discovery_loop/loop_state.json
reports/phase4_discovery_loop_report.md
```

### 停止条件

`no_active_hypotheses`：

```text
如果没有 active 假说，可以停止。
```

`no_experimental_feedback`：

```text
如果要求必须有实验反馈，而当前没有反馈，可以停止。
```

`reward_convergence`：

```text
当达到 min_iterations 后，如果 reward_mean 变化小于 delta，可以认为奖励收敛。
```

`max_iterations`：

```text
达到最大迭代数后停止。
```

## 文献检索意图机制

入口：

```text
sleep_ai_scientist/literature/experiment_intent.py
```

目标：

```text
实验结果 -> 新科学问题/证据缺口 -> LLM 和规则约束解析 -> 新 query
-> 新文献 -> 新 grounding -> 新 hypothesis
```

信号来源：

```text
failed primary tests
negative control failures
missing variables
modality gaps
high reward / validated pathways
critic findings / confounds
```

规则候选 query 类型：

```text
resolve_failed_test
probe_negative_control_failure
resolve_missing_measurement
fill_modality_gap
probe_confound_or_alternative_explanation
exploit_validated_pathway
```

LLM 候选：

```text
如果 literature.llm 配置启用，会要求 LLM 返回 strict JSON。
每个 intent 包含 intent_type、reason、priority、candidate_queries。
```

query 约束：

```text
1. 去重：不能和已有 configs/literature_queries.yaml 重复。
2. 长度：4 到 14 个 token。
3. 必须包含 sleep/insomnia/eeg/psg/fmri/dti/mri/rem/nrem/spindle 等领域词之一。
4. 不能包含内部 hypothesis_id / plan_id。
5. 不能像文件路径。
```

如果 accepted query 数量为 0：

```text
跳过文献刷新。
不会固定重复检索旧 query。
```

如果 accepted query 数量大于 0：

```text
1. 追加到 configs/literature_queries.yaml 的 experiment_feedback_expansion。
2. 写入 outputs/literature/query_expansion_intents.jsonl。
3. 写入 iteration_xxx/literature_expansion_plan.json。
4. 写入 iteration_xxx/literature_incremental_queries.yaml。
5. 使用 incremental query config 刷新 literature DB 和 RAG。
```

关键日志：

```text
[literature_intent] start iteration=...
[literature_intent] extracted signals failed_tests=... negative_control_failures=... missing_variables=... modality_gaps=...
[literature_intent] candidates generated=...
[literature_intent] accepted=... rejected_duplicate=... rejected_invalid=...
[literature_intent] appended query_config=... group=experiment_feedback_expansion count=...
[literature_refresh] incremental start new_queries=...
literature DB refreshed registry_records=... rag_chunks=... embedding_vectors=...
```

## Grounding 与下一轮 hypothesis 的关系

Grounding 生成的内容会影响下一轮 hypothesis：

```text
evidence_table / llm_evidence_context
  -> 提供支持或反驳机制的证据文本

mechanism_graph / llm_mechanism_context
  -> 提供机制节点、变量节点、边关系

evidence_to_variable_map
  -> 约束文献机制如何映射到真实变量

analysis_ready_profile
  -> 告诉假说排序当前数据是否能直接检验该假说

experimental_feedback
  -> 告诉假说系统上一轮哪些路径被支持、哪些失败、哪些负控失败
```

如果当前 `analysis_ready_profile` 是空或不可用，假说输入就主要来自 DB/RAG grounding 和已有先验，`data_testability` 会变成 `unknown`。

如果 profile 可用，假说排序会把科学强度和当前数据可检验性分开处理。

## 数据库与导出

数据库配置：

```text
configs/database_config.yaml
```

默认后端：

```text
PostgreSQL
```

本地开发和测试通常使用 SQLite：

```text
data/literature/sleep_literature.db
```

文献 registry 当前以 CSV 为主：

```text
data/literature/sleep_literature_registry.csv
```

RAG chunks 和 embedding 存储在数据库中。若后续流程不需要同名 JSONL，优先保留 CSV 和 DB 内数据，避免重复产物造成混淆。

## 日志

常见日志位置：

```text
logs/run_all_tests_*.log
logs/run_discovery_loop_*.log
logs/literature_db_build_start.log
logs/embedding_retrieval.log
```

关键日志前缀：

```text
[run_all_tests]
[run_discovery_loop]
[literature_build]
[api]
[embedding]
[grounding_topk_query]
[literature_intent]
[literature_refresh]
[experiment]
[hypothesis]
[discovery_loop]
```

## 当前结果解读注意事项

1. 主检验显著不等于机制已证明。

2. ML 预测能力说明变量组合能否泛化预测 outcome，不等于因果机制。

3. 负控失败是强风险信号。比如 predictor 同时强关联 global signal power，就说明结果可能受 global signal、motion、QC 或预处理影响。

4. DTI/FA、EEG/spindle、ISI/PSQI 等变量如果不在当前 profile 中，相关假说只能标为 partially_testable 或 not_directly_testable。

5. top-K 不能长期使用固定 query。后续迭代应优先使用实验反馈生成的动态 query。

6. feature importance 不能直接解释为神经机制强度，尤其不同 ML 模型的重要性尺度不一致。

## 推荐检查顺序

一次完整运行后，建议按这个顺序查看：

```text
1. logs/run_all_tests_*.log
2. outputs/discovery_loop/loop_state.json
3. outputs/discovery_loop/iteration_xxx/loop_summary.json
4. outputs/discovery_loop/iteration_xxx/hypothesis/top_k_hypotheses.json
5. outputs/discovery_loop/iteration_xxx/experiment/experiment_results.json
6. outputs/discovery_loop/iteration_xxx/experiment/experimental_feedback.json
7. outputs/discovery_loop/iteration_xxx/experiment/visuals/index.html
8. outputs/discovery_loop/iteration_xxx/literature_expansion_plan.json
9. outputs/discovery_loop/iteration_xxx/literature_incremental_queries.yaml
10. outputs/grounding/evidence_table.json
11. outputs/grounding/mechanism_graph.json
12. outputs/profiles/analysis_ready_profile.yaml
```

## 工程边界

当前工程已经实现了完整闭环的骨架和多阶段产物追踪，但仍需注意：

```text
1. 一些阶段仍依赖规则和模板，LLM 主要用于假说生成、评审或可选文献意图解析。
2. fMRI-only 数据无法直接验证 DTI/FA、EEG/spindle、临床量表严重程度等机制。
3. 文献 DB/RAG 的 registry/chunk 数量不一定每轮增加；只有 accepted new query 产生新检索结果时才会扩充。
4. 可视化是实验结果的解释辅助，不替代统计审查。
5. discovery loop 的每一轮都应以 `outputs/discovery_loop/iteration_xxx` 为准；全局 `outputs/experiments`、`outputs/hypotheses`、`outputs/features` 只表示单独运行阶段时的默认输出位置。
```
