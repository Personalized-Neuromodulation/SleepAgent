# 神经科学研究 Agent 中文报告

- 用户任务：做功能连接分析的创新性实验
- 输入数据目录：/media/qlp/68ACC1E8ACC1B13C/fmri_agent/fmri_result/JingZongOLT/fmri_free
- 中文文献报告：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/papers/literature_report_zh.md
- 被试：sub-ISM035
- Session：

## 最优候选范式

- Resting-state functional connectivity（`resting_state_functional_connectivity`）：82/100
- 当前数据是否可执行：True
- 执行状态：completed
- 缺失数据：[]

## 图表与 3D 结果

- score_bar_svg: /home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/figures/paradigm_scores.svg
- score_heatmap_svg: /home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/figures/paradigm_score_heatmap.svg
- innovation_01_resting_state_functional_connectivity_3d_connectome_html: /home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_01/resting_state_connectome_3d.html
- innovation_01_resting_state_functional_connectivity_topview_connectome_svg: /home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_01/resting_state_connectome_topview.svg
- innovation_02_dynamic_functional_connectivity_3d_connectome_html: /home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_02/dynamic_fc_connectome_3d.html
- innovation_02_dynamic_functional_connectivity_topview_connectome_svg: /home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_02/dynamic_fc_connectome_topview.svg
- innovation_06_graph_theory_connectomics_3d_connectome_html: /home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_06/resting_state_connectome_3d.html
- innovation_06_graph_theory_connectomics_topview_connectome_svg: /home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_06/resting_state_connectome_topview.svg

## 检索文献

- Dynamic functional connectivity in resting-state fMRI | https://pubmed.ncbi.nlm.nih.gov/22484408/
- Complex brain networks: graph theoretical analysis of structural and functional systems | https://pubmed.ncbi.nlm.nih.gov/19895843/
- A default mode of brain function | https://pubmed.ncbi.nlm.nih.gov/11209064/
- Information-based functional brain mapping | https://pubmed.ncbi.nlm.nih.gov/16497565/
- Mapping human brain networks with MEG and EEG | https://pubmed.ncbi.nlm.nih.gov/24174914/
- Multimodal integration in neuroimaging and neuroscience | https://pubmed.ncbi.nlm.nih.gov/23298758/
- Functional connectivity in the motor cortex of resting human brain using echo-planar MRI | https://pubmed.ncbi.nlm.nih.gov/8524021/
- Amplitude of low-frequency fluctuation and fractional ALFF in resting-state fMRI | https://pubmed.ncbi.nlm.nih.gov/17434757/
- Statistical parametric maps in functional imaging | https://pubmed.ncbi.nlm.nih.gov/8290352/
- Surface-based analysis of the human cerebral cortex | https://pubmed.ncbi.nlm.nih.gov/9931268/
- Analyzing neural time series data: theory and practice | https://mitpress.mit.edu/9780262019873/analyzing-neural-time-series-data/
- Event-related brain potentials in the study of cognition | https://pubmed.ncbi.nlm.nih.gov/7644493/
- The analysis of neural data | https://www.springer.com/gp/book/9780387987603
- Diffusion model analysis with hierarchical Bayesian estimation | https://pubmed.ncbi.nlm.nih.gov/23901278/
- Pupil size tracks perceptual content and surprise | https://pubmed.ncbi.nlm.nih.gov/23624365/
- Mapping structural brain networks with diffusion MRI | https://pubmed.ncbi.nlm.nih.gov/19895838/
- Positron emission tomography neuroreceptor imaging | https://pubmed.ncbi.nlm.nih.gov/16406884/
- Extracting neuronal activity from large-scale calcium imaging data | https://pubmed.ncbi.nlm.nih.gov/26774160/
- A transcriptomic and cell-type atlas of the human brain | https://pubmed.ncbi.nlm.nih.gov/27409810/

## 原始创新点

- `innovation_01` Resting-state functional connectivity: 提出“跨网络-小脑连接偏置指数”：同时比较网络内连接、跨网络连接和小脑相关连接的 Fisher-Z 强度，用一个方向性指标刻画单被试功能连接偏离模式。
  假设：目标被试的静息态功能连接中，默认网络、感觉运动网络和小脑相关 ROI 之间的连接强度会呈现可量化的不均衡模式；这种不均衡可作为单被试功能网络表型，而不是只报告平均相关矩阵。
- `innovation_02` Dynamic functional connectivity: 提出“单被试动态连接不稳定性曲线”：用滑窗 FC 的均值强度、矩阵距离和 top-edge 重排率刻画状态转移，而不是只给一个全程平均连接矩阵。
  假设：目标被试的功能连接不是静态稳定的，而是在扫描过程中出现若干高连接和低连接窗口；窗口间连接矩阵变化幅度可以反映状态切换特征。
- `innovation_03` ALFF/fALFF frequency-domain analysis: 提出“低频振幅-连接耦合检验”：将 ALFF/fALFF 摘要与 ROI 连接强度排序联合解释，区分局部振幅增强和网络连接增强。
  假设：目标被试的低频 BOLD 振幅在部分 ROI 或体素簇中增强，可能对应局部自发活动强度差异。
- `innovation_04` Surface-based cortical analysis: 提出“体积-表面一致性检查”：比较 surface BOLD 与 volume BOLD 的可用性和信号摘要，识别哪些结论依赖空间表达方式。
  假设：皮层表面空间中的 BOLD 信号变化比体素空间更能保留皮层拓扑特征，可能揭示体积分析中被平滑掩盖的局部差异。
- `innovation_05` Sleep-stage segmented analysis: 提出“睡眠-清醒连接重排指数”：直接比较 W/S 分段 clean BOLD 的 top edges、平均连接强度和 3D connectome 空间分布。
  假设：睡眠/清醒片段之间的功能连接拓扑不同，清醒期更可能表现为跨网络连接增强，睡眠期更可能表现为局部或低频同步增强。
- `innovation_06` Graph-theory connectomics: 提出“效率-模块化失衡画像”：在多个连接阈值下同时追踪节点度、全局效率和模块化趋势，用阈值稳定性而非单阈值图指标支持解释。
  假设：功能连接图的全局效率和局部模块化之间存在单被试层面的权衡，提示网络整合与分离的平衡状态。
- `innovation_07` Behavioral computational modeling: 提出“连接表型驱动的行为潜变量模型”：把 FC 偏置、动态不稳定性和图指标作为潜变量候选，而不是直接把行为分数与全脑平均连接做相关。
  假设：如果后续补充行为指标，单被试功能连接偏置可以作为计算模型中的潜变量，解释反应速度、准确率或状态评分的个体内波动。
- `innovation_08` Structural MRI morphometry: 提出基于 Structural MRI morphometry 输出的单被试机制检验：把主要指标、预期方向和替代解释同时纳入创新假设，而不是只报告范式结果。
  假设：Structural MRI morphometry 可以从当前数据中提取一个可量化的神经表型，但必须明确该表型对应的机制解释和失败条件。

## 创新点实验目录

### `innovation_01`
- 实验文件夹：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_01
- 绑定范式：resting_state_functional_connectivity
- `resting_state_functional_connectivity` py代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_01/resting_state_functional_connectivity.py
  执行状态：completed，结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_01/resting_state_functional_connectivity_result.json
### `innovation_02`
- 实验文件夹：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_02
- 绑定范式：dynamic_functional_connectivity
- `dynamic_functional_connectivity` py代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_02/dynamic_functional_connectivity.py
  执行状态：completed，结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_02/dynamic_functional_connectivity_result.json
### `innovation_03`
- 实验文件夹：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_03
- 绑定范式：alff_falff_frequency
- `alff_falff_frequency` py代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_03/alff_falff_frequency.py
  执行状态：completed，结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_03/alff_falff_frequency_result.json
### `innovation_04`
- 实验文件夹：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_04
- 绑定范式：surface_based_analysis
- `surface_based_analysis` py代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_04/surface_based_analysis.py
  执行状态：not_executable，结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_04/surface_based_analysis_result.json
### `innovation_05`
- 实验文件夹：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_05
- 绑定范式：sleep_stage_analysis
- `sleep_stage_analysis` py代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_05/sleep_stage_analysis.py
  执行状态：completed，结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_05/sleep_stage_analysis_result.json
### `innovation_06`
- 实验文件夹：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_06
- 绑定范式：graph_theory_connectomics
- `graph_theory_connectomics` py代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_06/graph_theory_connectomics.py
  执行状态：completed，结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_06/graph_theory_connectomics_result.json
### `innovation_07`
- 实验文件夹：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_07
- 绑定范式：behavioral_computational_modeling
- `behavioral_computational_modeling` py代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_07/behavioral_computational_modeling.py
  执行状态：completed，结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_07/behavioral_computational_modeling_result.json
### `innovation_08`
- 实验文件夹：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_08
- 绑定范式：structural_morphometry
- `structural_morphometry` py代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_08/structural_morphometry.py
  执行状态：completed，结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_08/structural_morphometry_result.json

## 根据真实执行结果反向修正创新点

- 总体结论：
- 更新方法：llm_experimental_feedback_update
### `innovation_01`
- 原始创新点：提出“跨网络-小脑连接偏置指数”：同时比较网络内连接、跨网络连接和小脑相关连接的 Fisher-Z 强度，用一个方向性指标刻画单被试功能连接偏离模式。
- 执行结果解释：LLM 未返回该创新点的单独更新，保持原始创新点。
- 修正后假设：目标被试的静息态功能连接中，默认网络、感觉运动网络和小脑相关 ROI 之间的连接强度会呈现可量化的不均衡模式；这种不均衡可作为单被试功能网络表型，而不是只报告平均相关矩阵。
- 修正后创新点：提出“跨网络-小脑连接偏置指数”：同时比较网络内连接、跨网络连接和小脑相关连接的 Fisher-Z 强度，用一个方向性指标刻画单被试功能连接偏离模式。
- 下一步实验：人工检查执行结果后再决定是否修订。
- 置信度：low
### `innovation_02`
- 原始创新点：提出“单被试动态连接不稳定性曲线”：用滑窗 FC 的均值强度、矩阵距离和 top-edge 重排率刻画状态转移，而不是只给一个全程平均连接矩阵。
- 执行结果解释：LLM 未返回该创新点的单独更新，保持原始创新点。
- 修正后假设：目标被试的功能连接不是静态稳定的，而是在扫描过程中出现若干高连接和低连接窗口；窗口间连接矩阵变化幅度可以反映状态切换特征。
- 修正后创新点：提出“单被试动态连接不稳定性曲线”：用滑窗 FC 的均值强度、矩阵距离和 top-edge 重排率刻画状态转移，而不是只给一个全程平均连接矩阵。
- 下一步实验：人工检查执行结果后再决定是否修订。
- 置信度：low
### `innovation_03`
- 原始创新点：提出“低频振幅-连接耦合检验”：将 ALFF/fALFF 摘要与 ROI 连接强度排序联合解释，区分局部振幅增强和网络连接增强。
- 执行结果解释：LLM 未返回该创新点的单独更新，保持原始创新点。
- 修正后假设：目标被试的低频 BOLD 振幅在部分 ROI 或体素簇中增强，可能对应局部自发活动强度差异。
- 修正后创新点：提出“低频振幅-连接耦合检验”：将 ALFF/fALFF 摘要与 ROI 连接强度排序联合解释，区分局部振幅增强和网络连接增强。
- 下一步实验：人工检查执行结果后再决定是否修订。
- 置信度：low
### `innovation_04`
- 原始创新点：提出“体积-表面一致性检查”：比较 surface BOLD 与 volume BOLD 的可用性和信号摘要，识别哪些结论依赖空间表达方式。
- 执行结果解释：LLM 未返回该创新点的单独更新，保持原始创新点。
- 修正后假设：皮层表面空间中的 BOLD 信号变化比体素空间更能保留皮层拓扑特征，可能揭示体积分析中被平滑掩盖的局部差异。
- 修正后创新点：提出“体积-表面一致性检查”：比较 surface BOLD 与 volume BOLD 的可用性和信号摘要，识别哪些结论依赖空间表达方式。
- 下一步实验：人工检查执行结果后再决定是否修订。
- 置信度：low
### `innovation_05`
- 原始创新点：提出“睡眠-清醒连接重排指数”：直接比较 W/S 分段 clean BOLD 的 top edges、平均连接强度和 3D connectome 空间分布。
- 执行结果解释：LLM 未返回该创新点的单独更新，保持原始创新点。
- 修正后假设：睡眠/清醒片段之间的功能连接拓扑不同，清醒期更可能表现为跨网络连接增强，睡眠期更可能表现为局部或低频同步增强。
- 修正后创新点：提出“睡眠-清醒连接重排指数”：直接比较 W/S 分段 clean BOLD 的 top edges、平均连接强度和 3D connectome 空间分布。
- 下一步实验：人工检查执行结果后再决定是否修订。
- 置信度：low
### `innovation_06`
- 原始创新点：提出“效率-模块化失衡画像”：在多个连接阈值下同时追踪节点度、全局效率和模块化趋势，用阈值稳定性而非单阈值图指标支持解释。
- 执行结果解释：LLM 未返回该创新点的单独更新，保持原始创新点。
- 修正后假设：功能连接图的全局效率和局部模块化之间存在单被试层面的权衡，提示网络整合与分离的平衡状态。
- 修正后创新点：提出“效率-模块化失衡画像”：在多个连接阈值下同时追踪节点度、全局效率和模块化趋势，用阈值稳定性而非单阈值图指标支持解释。
- 下一步实验：人工检查执行结果后再决定是否修订。
- 置信度：low
### `innovation_07`
- 原始创新点：提出“连接表型驱动的行为潜变量模型”：把 FC 偏置、动态不稳定性和图指标作为潜变量候选，而不是直接把行为分数与全脑平均连接做相关。
- 执行结果解释：LLM 未返回该创新点的单独更新，保持原始创新点。
- 修正后假设：如果后续补充行为指标，单被试功能连接偏置可以作为计算模型中的潜变量，解释反应速度、准确率或状态评分的个体内波动。
- 修正后创新点：提出“连接表型驱动的行为潜变量模型”：把 FC 偏置、动态不稳定性和图指标作为潜变量候选，而不是直接把行为分数与全脑平均连接做相关。
- 下一步实验：人工检查执行结果后再决定是否修订。
- 置信度：low
### `innovation_08`
- 原始创新点：提出基于 Structural MRI morphometry 输出的单被试机制检验：把主要指标、预期方向和替代解释同时纳入创新假设，而不是只报告范式结果。
- 执行结果解释：LLM 未返回该创新点的单独更新，保持原始创新点。
- 修正后假设：Structural MRI morphometry 可以从当前数据中提取一个可量化的神经表型，但必须明确该表型对应的机制解释和失败条件。
- 修正后创新点：提出基于 Structural MRI morphometry 输出的单被试机制检验：把主要指标、预期方向和替代解释同时纳入创新假设，而不是只报告范式结果。
- 下一步实验：人工检查执行结果后再决定是否修订。
- 置信度：low

## 创新点评分

| 创新点 | 总分 | 新颖性 | 可行性 | 科学价值 | 风险控制 |
| --- | ---: | ---: | ---: | ---: | ---: |
| innovation_01 | 86 | 16 | 20 | 25 | 25 |
| innovation_02 | 84 | 16 | 19 | 24 | 25 |
| innovation_03 | 84 | 16 | 18 | 25 | 25 |
| innovation_06 | 84 | 16 | 19 | 24 | 25 |
| innovation_07 | 83 | 16 | 17 | 25 | 25 |
| innovation_05 | 82 | 16 | 17 | 24 | 25 |
| innovation_08 | 81 | 16 | 16 | 24 | 25 |
| innovation_04 | 78 | 16 | 18 | 24 | 20 |

## 范式评分

| 范式 | 可执行 | 分数 | 缺失数据 |
| --- | --- | ---: | --- |
| resting_state_functional_connectivity | True | 82 | [] |
| dynamic_functional_connectivity | True | 79 | [] |
| graph_theory_connectomics | True | 79 | [] |
| surface_based_analysis | True | 75 | [] |
| alff_falff_frequency | True | 74 | [] |
| sleep_stage_analysis | True | 71 | [] |
| behavioral_computational_modeling | True | 68 | [] |
| structural_morphometry | True | 65 | [] |
| eeg_meg_time_frequency | False | 61 | ['eeg'] |
| multimodal_neuroscience_fusion | False | 61 | ['labels'] |
| source_connectivity | False | 56 | ['eeg'] |
| spike_train_statistics | False | 56 | ['ephys_spikes'] |
| calcium_population_dynamics | False | 56 | ['calcium_imaging'] |
| task_glm | False | 53 | ['events'] |
| eye_tracking_pupil_gaze | False | 53 | ['eye_tracking'] |
| diffusion_connectomics | False | 53 | ['dwi'] |
| mvpa_decoding | False | 47 | ['labels'] |
| pet_neurochemistry | False | 47 | ['pet'] |
| neurogenomics_association | False | 47 | ['omics'] |
| lfp_spectral_coupling | False | 46 | ['lfp'] |
| erp_evoked_response | False | 41 | ['eeg', 'events'] |

## 范式执行详情

### Resting-state functional connectivity (`resting_state_functional_connectivity`)
- 分数：82/100
- 生成代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_01/resting_state_functional_connectivity.py
- 执行：completed returncode=0
- 结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_01/resting_state_functional_connectivity_result.json
- 缺失数据：[]
### Dynamic functional connectivity (`dynamic_functional_connectivity`)
- 分数：79/100
- 生成代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_02/dynamic_functional_connectivity.py
- 执行：completed returncode=0
- 结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_02/dynamic_functional_connectivity_result.json
- 缺失数据：[]
### Graph-theory connectomics (`graph_theory_connectomics`)
- 分数：79/100
- 生成代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_06/graph_theory_connectomics.py
- 执行：completed returncode=0
- 结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_06/graph_theory_connectomics_result.json
- 缺失数据：[]
### Surface-based cortical analysis (`surface_based_analysis`)
- 分数：75/100
- 生成代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_04/surface_based_analysis.py
- 执行：not_executable returncode=0
- 结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_04/surface_based_analysis_result.json
- 缺失数据：[]
### ALFF/fALFF frequency-domain analysis (`alff_falff_frequency`)
- 分数：74/100
- 生成代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_03/alff_falff_frequency.py
- 执行：completed returncode=0
- 结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_03/alff_falff_frequency_result.json
- 缺失数据：[]
### Sleep-stage segmented analysis (`sleep_stage_analysis`)
- 分数：71/100
- 生成代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_05/sleep_stage_analysis.py
- 执行：completed returncode=0
- 结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_05/sleep_stage_analysis_result.json
- 缺失数据：[]
### Behavioral computational modeling (`behavioral_computational_modeling`)
- 分数：68/100
- 生成代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_07/behavioral_computational_modeling.py
- 执行：completed returncode=0
- 结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_07/behavioral_computational_modeling_result.json
- 缺失数据：[]
### Structural MRI morphometry (`structural_morphometry`)
- 分数：65/100
- 生成代码：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_08/structural_morphometry.py
- 执行：completed returncode=0
- 结果 JSON：/home/qlp/Agent_skills/neuroscience_research_agent/outputs/20260622_095011/experiments/innovation_08/structural_morphometry_result.json
- 缺失数据：[]
### EEG/MEG time-frequency analysis (`eeg_meg_time_frequency`)
- 分数：61/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['eeg']
### Multimodal neuroscience fusion (`multimodal_neuroscience_fusion`)
- 分数：61/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['labels']
### Source-space neural connectivity (`source_connectivity`)
- 分数：56/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['eeg']
### Spike-train statistics (`spike_train_statistics`)
- 分数：56/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['ephys_spikes']
### Calcium-imaging population dynamics (`calcium_population_dynamics`)
- 分数：56/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['calcium_imaging']
### Task-fMRI GLM (`task_glm`)
- 分数：53/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['events']
### Eye-tracking pupil and gaze analysis (`eye_tracking_pupil_gaze`)
- 分数：53/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['eye_tracking']
### Diffusion MRI connectomics (`diffusion_connectomics`)
- 分数：53/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['dwi']
### MVPA / decoding (`mvpa_decoding`)
- 分数：47/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['labels']
### PET neurochemistry analysis (`pet_neurochemistry`)
- 分数：47/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['pet']
### Neurogenomics association analysis (`neurogenomics_association`)
- 分数：47/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['omics']
### LFP spectral coupling (`lfp_spectral_coupling`)
- 分数：46/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['lfp']
### ERP / evoked-response analysis (`erp_evoked_response`)
- 分数：41/100
- 生成代码：
- 执行：not_run returncode=
- 结果 JSON：
- 缺失数据：['eeg', 'events']

## 代码资源

### resting_state_functional_connectivity
- nilearn connectivity examples: https://nilearn.github.io/stable/connectivity/index.html
### dynamic_functional_connectivity
- NWB/PyNWB: https://pynwb.readthedocs.io/
### alff_falff_frequency
- nilearn signal cleaning: https://nilearn.github.io/
### surface_based_analysis
- NWB/PyNWB: https://pynwb.readthedocs.io/
### sleep_stage_analysis
- NWB/PyNWB: https://pynwb.readthedocs.io/
### graph_theory_connectomics
- NWB/PyNWB: https://pynwb.readthedocs.io/
### behavioral_computational_modeling
- HDDM: https://hddm.readthedocs.io/
### structural_morphometry
- NWB/PyNWB: https://pynwb.readthedocs.io/
