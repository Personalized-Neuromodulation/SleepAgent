# 创新点生成过程

## 用户问题

做功能连接分析的创新性实验

## 方法概述

1. LLM 根据用户问题、文献和候选范式生成多条候选创新点。
2. 每条候选创新点生成后进行自我反思，检查新颖性、可证伪性、缺失数据依赖和风险控制。
3. 自我反思后不再做统一评审，而是采用 pairwise tournament：每次比较两个 idea，记录胜者、败者和中文理由。
4. 将所有胜负关系输入 Bradley-Terry-Luce 排序；优先使用 `choix.ilsr_pairwise`，失败时使用本地 BTL 排序。
5. 实验/计算执行完成后，根据 execution_results 反向更新每个创新点；如果没有执行结果，也会记录“尚未被结果检验”的更新状态。

## innovation_01：Resting-state functional connectivity

- 创新点：提出“跨网络-小脑连接偏置指数”：同时比较网络内连接、跨网络连接和小脑相关连接的 Fisher-Z 强度，用一个方向性指标刻画单被试功能连接偏离模式。
- 科学假设：目标被试的静息态功能连接中，默认网络、感觉运动网络和小脑相关 ROI 之间的连接强度会呈现可量化的不均衡模式；这种不均衡可作为单被试功能网络表型，而不是只报告平均相关矩阵。
- 提出依据：数据驱动候选生成：先把候选范式视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该范式候选得分为 23；当前数据满足该范式的基础输入要求。相关文献用于约束解释边界：Dynamic functional connectivity in resting-state fMRI; Complex brain networks: graph theoretical analysis of structural and functional systems。
- 新颖性说明：该创新点不是简单运行既有范式，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。

### 自我反思过程

- LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选范式生成具体机制假设和预期结果。
- 自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。

### Pairwise Tournament 排序过程

- LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选范式排序生成。

### 实验结果反向更新

- 已找到该创新点关联的真实执行结果：resting_state_functional_connectivity。这些结果可作为初步证据，但当前自动更新只基于执行状态和 result.json 结构化摘要，不能夸大为显著科学发现；需要继续查看关键指标、图形和跨被试稳定性。 结果文件：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_174323/experiments/innovation_01/resting_state_functional_connectivity_result.json。

## innovation_02：Dynamic functional connectivity

- 创新点：提出“单被试动态连接不稳定性曲线”：用滑窗 FC 的均值强度、矩阵距离和 top-edge 重排率刻画状态转移，而不是只给一个全程平均连接矩阵。
- 科学假设：目标被试的功能连接不是静态稳定的，而是在扫描过程中出现若干高连接和低连接窗口；窗口间连接矩阵变化幅度可以反映状态切换特征。
- 提出依据：数据驱动候选生成：先把候选范式视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该范式候选得分为 20；当前数据满足该范式的基础输入要求。相关文献用于约束解释边界：Dynamic functional connectivity in resting-state fMRI; Complex brain networks: graph theoretical analysis of structural and functional systems。
- 新颖性说明：该创新点不是简单运行既有范式，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。

### 自我反思过程

- LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选范式生成具体机制假设和预期结果。
- 自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。

### Pairwise Tournament 排序过程

- LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选范式排序生成。

### 实验结果反向更新

- 已找到该创新点关联的真实执行结果：dynamic_functional_connectivity。这些结果可作为初步证据，但当前自动更新只基于执行状态和 result.json 结构化摘要，不能夸大为显著科学发现；需要继续查看关键指标、图形和跨被试稳定性。 结果文件：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_174323/experiments/innovation_02/dynamic_functional_connectivity_result.json。

## innovation_03：ALFF/fALFF frequency-domain analysis

- 创新点：提出“低频振幅-连接耦合检验”：将 ALFF/fALFF 摘要与 ROI 连接强度排序联合解释，区分局部振幅增强和网络连接增强。
- 科学假设：目标被试的低频 BOLD 振幅在部分 ROI 或体素簇中增强，可能对应局部自发活动强度差异。
- 提出依据：数据驱动候选生成：先把候选范式视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该范式候选得分为 20；当前数据满足该范式的基础输入要求。相关文献用于约束解释边界：Dynamic functional connectivity in resting-state fMRI; Complex brain networks: graph theoretical analysis of structural and functional systems。
- 新颖性说明：该创新点不是简单运行既有范式，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。

### 自我反思过程

- LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选范式生成具体机制假设和预期结果。
- 自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。

### Pairwise Tournament 排序过程

- LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选范式排序生成。

### 实验结果反向更新

- 已找到该创新点关联的真实执行结果：alff_falff_frequency。这些结果可作为初步证据，但当前自动更新只基于执行状态和 result.json 结构化摘要，不能夸大为显著科学发现；需要继续查看关键指标、图形和跨被试稳定性。 结果文件：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_174323/experiments/innovation_03/alff_falff_frequency_result.json。

## innovation_04：Surface-based cortical analysis

- 创新点：提出“体积-表面一致性检查”：比较 surface BOLD 与 volume BOLD 的可用性和信号摘要，识别哪些结论依赖空间表达方式。
- 科学假设：皮层表面空间中的 BOLD 信号变化比体素空间更能保留皮层拓扑特征，可能揭示体积分析中被平滑掩盖的局部差异。
- 提出依据：数据驱动候选生成：先把候选范式视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该范式候选得分为 20；当前数据满足该范式的基础输入要求。相关文献用于约束解释边界：Dynamic functional connectivity in resting-state fMRI; Complex brain networks: graph theoretical analysis of structural and functional systems。
- 新颖性说明：该创新点不是简单运行既有范式，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。

### 自我反思过程

- LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选范式生成具体机制假设和预期结果。
- 自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。

### Pairwise Tournament 排序过程

- LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选范式排序生成。

### 实验结果反向更新

- 关联实验未成功完成：surface_based_analysis。当前不能用实验结果支持或削弱该创新点，反向更新应优先修正可执行性、数据依赖和失败条件。

## innovation_05：Sleep-stage segmented analysis

- 创新点：提出“睡眠-清醒连接重排指数”：直接比较 W/S 分段 clean BOLD 的 top edges、平均连接强度和 3D connectome 空间分布。
- 科学假设：睡眠/清醒片段之间的功能连接拓扑不同，清醒期更可能表现为跨网络连接增强，睡眠期更可能表现为局部或低频同步增强。
- 提出依据：数据驱动候选生成：先把候选范式视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该范式候选得分为 20；当前数据满足该范式的基础输入要求。相关文献用于约束解释边界：Dynamic functional connectivity in resting-state fMRI; Complex brain networks: graph theoretical analysis of structural and functional systems。
- 新颖性说明：该创新点不是简单运行既有范式，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。

### 自我反思过程

- LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选范式生成具体机制假设和预期结果。
- 自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。

### Pairwise Tournament 排序过程

- LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选范式排序生成。

### 实验结果反向更新

- 已找到该创新点关联的真实执行结果：sleep_stage_analysis。这些结果可作为初步证据，但当前自动更新只基于执行状态和 result.json 结构化摘要，不能夸大为显著科学发现；需要继续查看关键指标、图形和跨被试稳定性。 结果文件：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_174323/experiments/innovation_05/sleep_stage_analysis_result.json。

## innovation_06：Graph-theory connectomics

- 创新点：提出“效率-模块化失衡画像”：在多个连接阈值下同时追踪节点度、全局效率和模块化趋势，用阈值稳定性而非单阈值图指标支持解释。
- 科学假设：功能连接图的全局效率和局部模块化之间存在单被试层面的权衡，提示网络整合与分离的平衡状态。
- 提出依据：数据驱动候选生成：先把候选范式视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该范式候选得分为 20；当前数据满足该范式的基础输入要求。相关文献用于约束解释边界：Dynamic functional connectivity in resting-state fMRI; Complex brain networks: graph theoretical analysis of structural and functional systems。
- 新颖性说明：该创新点不是简单运行既有范式，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。

### 自我反思过程

- LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选范式生成具体机制假设和预期结果。
- 自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。

### Pairwise Tournament 排序过程

- LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选范式排序生成。

### 实验结果反向更新

- 已找到该创新点关联的真实执行结果：graph_theory_connectomics。这些结果可作为初步证据，但当前自动更新只基于执行状态和 result.json 结构化摘要，不能夸大为显著科学发现；需要继续查看关键指标、图形和跨被试稳定性。 结果文件：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_174323/experiments/innovation_06/graph_theory_connectomics_result.json。

## innovation_07：Behavioral computational modeling

- 创新点：提出“连接表型驱动的行为潜变量模型”：把 FC 偏置、动态不稳定性和图指标作为潜变量候选，而不是直接把行为分数与全脑平均连接做相关。
- 科学假设：如果后续补充行为指标，单被试功能连接偏置可以作为计算模型中的潜变量，解释反应速度、准确率或状态评分的个体内波动。
- 提出依据：数据驱动候选生成：先把候选范式视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该范式候选得分为 20；当前数据满足该范式的基础输入要求。相关文献用于约束解释边界：Dynamic functional connectivity in resting-state fMRI; Complex brain networks: graph theoretical analysis of structural and functional systems。
- 新颖性说明：该创新点不是简单运行既有范式，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。

### 自我反思过程

- LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选范式生成具体机制假设和预期结果。
- 自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。

### Pairwise Tournament 排序过程

- LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选范式排序生成。

### 实验结果反向更新

- 已找到该创新点关联的真实执行结果：behavioral_computational_modeling。这些结果可作为初步证据，但当前自动更新只基于执行状态和 result.json 结构化摘要，不能夸大为显著科学发现；需要继续查看关键指标、图形和跨被试稳定性。 结果文件：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_174323/experiments/innovation_07/behavioral_computational_modeling_result.json。

## innovation_08：Structural MRI morphometry

- 创新点：提出基于 Structural MRI morphometry 输出的单被试机制检验：把主要指标、预期方向和替代解释同时纳入创新假设，而不是只报告范式结果。
- 科学假设：Structural MRI morphometry 可以从当前数据中提取一个可量化的神经表型，但必须明确该表型对应的机制解释和失败条件。
- 提出依据：数据驱动候选生成：先把候选范式视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该范式候选得分为 20；当前数据满足该范式的基础输入要求。相关文献用于约束解释边界：Dynamic functional connectivity in resting-state fMRI; Complex brain networks: graph theoretical analysis of structural and functional systems。
- 新颖性说明：该创新点不是简单运行既有范式，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。

### 自我反思过程

- LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选范式生成具体机制假设和预期结果。
- 自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。

### Pairwise Tournament 排序过程

- LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选范式排序生成。

### 实验结果反向更新

- 已找到该创新点关联的真实执行结果：structural_morphometry。这些结果可作为初步证据，但当前自动更新只基于执行状态和 result.json 结构化摘要，不能夸大为显著科学发现；需要继续查看关键指标、图形和跨被试稳定性。 结果文件：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_174323/experiments/innovation_08/structural_morphometry_result.json。

## 实验结果整体反向更新

已根据真实执行结果为每个创新点生成反向更新；LLM 缺失或 ID 不规范的条目已由本地执行结果兜底补齐。
