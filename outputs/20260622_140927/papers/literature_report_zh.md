# 中文文献检索报告

## 研究任务

做功能连接分析的创新性实验

## 检索设置

- 允许联网检索：是
- 检索规划模型：gemma4:latest
- 检索查询：做功能连接分析的创新性实验, novel functional connectivity paradigms for neuroimaging, innovative resting-state functional connectivity analysis techniques, task-based functional connectivity novel experimental designs, machine learning approaches for functional connectivity analysis in neurodevelopmental disorders
- 检索策略说明：用户目标是进行功能连接分析的创新性实验，旨在收集100篇文献。因此，查询需要覆盖“创新性”（novel/innovative）、“功能连接”（functional connectivity, FC）和“实验设计/分析方法”（paradigms, techniques, machine learning, multi-modal）等核心概念。查询涵盖了从实验范式（如任务型、静息态）到高级分析方法（如机器学习、多模态）的广度，以确保检索结果的创新性和多样性，从而达到收集大量相关文献的目的。

## 总体判断

用户希望设计具有创新性的功能连接分析实验。从提供的文献来看，最核心的创新点在于：1. **时间维度**：从静态连接（fMRI）转向动态连接（DFC，论文6）。2. **网络拓扑维度**：从连接强度转向网络结构（图论，论文7）。3. **时间分辨率维度**：从BOLD信号转向快电生理信号（MEG/EEG，论文11）。4. **机制解释维度**：从单纯的连接发现转向多模态的机制解释（论文19）。因此，建议将这些方法论（6, 7, 11）结合起来，例如，使用MEG/EEG捕捉快速连接，并用图论分析其动态变化，最后结合行为或分子数据进行机制验证，以达到最高的创新性。

## 入选文献

### 1. Dynamic functional connectivity in resting-state fMRI

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/22484408/
- 相关性评分：95
- 证据质量：high
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文6专门讨论了动态功能连接（DFC），这是功能连接分析的一个重要且前沿的创新方向，提供了具体的分析方法（滑动窗口和状态空间方法）。
- 中文摘要压缩：动态功能连接（DFC）研究可以表征大脑连接模式随时间的变化。通过使用滑动窗口或基于状态的方法，可以识别出时间变化的连接模式，从而超越了传统的静态连接分析。
- 主要贡献：提出了使用滑动窗口和状态空间方法来分析和表征时间变化的连接模式，为进行更精细、更动态的功能连接分析提供了理论和方法基础。
- 局限性：虽然提供了方法论，但没有具体指出在哪些类型的认知任务或疾病状态下进行创新性实验的指导，需要结合其他论文进行任务设计。

### 2. Complex brain networks: graph theoretical analysis of structural and functional systems

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/19895843/
- 相关性评分：90
- 证据质量：high
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文7介绍了图论（Graph Theory）在脑网络分析中的应用，这是从传统统计连接分析向更复杂的网络拓扑学分析转变的代表性创新方法，提供了新的指标（如模块度和效率）。
- 中文摘要压缩：图论为理解整个大脑网络结构提供了强大的工具。它提供了一系列网络组织指标，例如模块度（modularity）和效率（efficiency），用于量化大脑网络如何组织和运作。
- 主要贡献：将图论理论引入功能连接分析，允许研究人员从传统的连接强度转向分析网络拓扑结构，从而获得更丰富的网络组织信息。
- 局限性：主要侧重于理论和指标的介绍，缺乏具体的实验范式或如何将这些指标与行为学任务进行结合的指导。

### 3. Mapping human brain networks with MEG and EEG

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/24174914/
- 相关性评分：85
- 证据质量：high
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文11讨论了使用MEG和EEG等电生理信号进行脑网络分析，这些方法能够捕捉到比fMRI更快的神经信号（快神经通讯），这本身就是功能连接分析的重大创新方向。
- 中文摘要压缩：介绍了使用MEG和EEG等电生理信号进行源定位和连接分析。这些方法能够表征快速的神经通讯，提供了比血氧水平依赖（BOLD）信号更时间分辨率更高的功能连接视角。
- 主要贡献：强调了电生理信号（MEG/EEG）在功能连接分析中的应用，能够捕捉到快速的神经活动和连接，弥补了fMRI时间分辨率的不足，是功能连接分析的重大技术创新。
- 局限性：主要侧重于技术和信号处理，缺乏关于如何设计认知任务来最大化地利用这些快速连接信息的具体指导。

### 4. A default mode of brain function

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/11209064/
- 相关性评分：80
- 证据质量：medium
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文2介绍了默认模式网络（DMN），DMN是功能连接分析中最经典、最常被研究的网络之一。虽然本身不是“创新方法”，但它是功能连接分析的经典目标网络，任何创新实验都可能围绕DMN的异常或重组展开，具有重要的背景参考价值。
- 中文摘要压缩：默认模式网络（DMN）是脑功能的一个基础目标网络。它在休息状态下活动，是认知神经科学和临床神经科学研究的基石。
- 主要贡献：确立了DMN作为功能连接分析的经典和核心研究目标，为后续的异常连接或功能重组研究提供了基础框架。
- 局限性：内容过于基础和经典，本身不构成“创新性实验”的方法论指导，更多是研究的背景和目标设定。

### 5. Multimodal integration in neuroimaging and neuroscience

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/23298758/
- 相关性评分：75
- 证据质量：medium
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文19讨论了多模态整合，这是当前神经科学研究的最高级创新趋势。通过结合多种模态（如连接组学、转录组学、行为数据），可以从机制上解释功能连接的改变，极大地提升了实验的深度和创新性。
- 中文摘要压缩：强调了在神经影像学和神经科学中整合多模态数据的重要性。当每种模态都能提供互补的约束时，可以提高对神经机制的解释力。
- 主要贡献：提出了多模态数据整合的框架，指导研究人员不能仅停留在功能连接的统计发现，而必须结合分子、细胞或行为数据进行机制解释，这是提升实验创新性的关键。
- 局限性：这是一个宏观的理论框架，没有提供具体的实验流程或技术指导，需要研究者自行设计如何将不同模态数据结合起来。

### 6. Functional connectivity in the motor cortex of resting human brain using echo-planar MRI

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/8524021/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Resting-state fMRI can reveal coherent low-frequency BOLD correlations between functionally related brain regions.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 7. Amplitude of low-frequency fluctuation and fractional ALFF in resting-state fMRI

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/17434757/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：ALFF/fALFF summarize regional low-frequency spontaneous activity and are common complements to connectivity analyses.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 8. Statistical parametric maps in functional imaging

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/8290352/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：GLM-based contrast estimation is a standard task-fMRI paradigm for testing activation hypotheses.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 9. Information-based functional brain mapping

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/16497565/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：MVPA/decoding tests whether distributed activity patterns carry task or condition information.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 10. Surface-based analysis of the human cerebral cortex

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/9931268/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Surface-based analysis improves cortical alignment and enables cortical sheet-specific metrics.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 11. Analyzing neural time series data: theory and practice

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://mitpress.mit.edu/9780262019873/analyzing-neural-time-series-data/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Spectral and time-frequency methods quantify oscillatory neural dynamics across EEG, MEG, and local field potentials.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 12. Event-related brain potentials in the study of cognition

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/7644493/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：ERP components provide time-resolved markers of event-locked perceptual and cognitive processing.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 13. The analysis of neural data

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://www.springer.com/gp/book/9780387987603
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Spike-train statistics and population models provide quantitative tests of neural coding hypotheses.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 14. Diffusion model analysis with hierarchical Bayesian estimation

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/23901278/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Computational models of behavior can separate latent decision parameters from accuracy and reaction-time data.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 15. Pupil size tracks perceptual content and surprise

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/23624365/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Pupil and gaze features can index attention, arousal, uncertainty, and sampling behavior.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 16. Mapping structural brain networks with diffusion MRI

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/19895838/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Diffusion MRI supports white-matter tract and structural connectome hypotheses.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 17. Positron emission tomography neuroreceptor imaging

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/16406884/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：PET receptor and metabolism measurements provide neurochemical constraints on neural mechanisms.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 18. Extracting neuronal activity from large-scale calcium imaging data

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/26774160/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Calcium imaging pipelines estimate neural population activity and ensemble dynamics from optical recordings.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。

### 19. A transcriptomic and cell-type atlas of the human brain

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/27409810/
- 相关性评分：0
- 证据质量：seed
- 证据质量理由：基于关键词匹配和引用数的确定性回退评价。
- 中文摘要压缩：Transcriptomic and cell-type features can be linked to systems neuroscience phenotypes and disease mechanisms.
- 主要贡献：为当前研究任务提供相关背景或方法依据。
- 局限性：未经过 LLM 深度筛选；需要人工阅读原文确认。
