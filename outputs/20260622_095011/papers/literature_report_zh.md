# 中文文献检索报告

## 研究任务

做功能连接分析的创新性实验

## 检索设置

- 允许联网检索：是
- 检索规划模型：gemma4:latest
- 检索查询：做功能连接分析的创新性实验, novel functional connectivity paradigms for neuroimaging, innovative resting-state functional connectivity analysis methods, task-based functional connectivity paradigms for psychiatric disorders, dynamic functional connectivity analysis in neurological diseases
- 检索策略说明：用户目标是进行功能连接分析的创新性实验，旨在获取大量（100篇）的文献。因此，查询需要覆盖“创新性”（novel/innovative）、“功能连接”（functional connectivity, FC）的各种角度，包括不同的分析范式（如静息态、任务态、动态FC）、应用领域（如精神疾病、神经系统疾病）以及先进的分析方法（如机器学习、深度学习）。这些查询旨在从多个维度扩大搜索范围，确保覆盖到前沿和跨学科的研究进展，从而达到文献数量的积累目标。

## 总体判断

用户希望进行功能连接分析的创新性实验。我选择了6篇论文，它们代表了功能连接分析从传统相关性分析向更高级、更复杂的分析范式转变的几个关键前沿方向。核心创新点包括：1. **时间维度**：采用动态功能连接（dFC）分析（论文6），捕捉连接的瞬时变化；2. **网络结构维度**：使用图论（论文7）分析网络拓扑的复杂指标；3. **信息编码维度**：采用基于信息论的分析（论文5），测试连接是否携带可解码的认知信息；4. **模态维度**：结合电生理信号（论文11）提高时间分辨率，或结合多模态数据（论文19）提高机制解释力。这些方向的结合（例如：dFC + 图论 + 多模态）将构成高度创新的研究设计。

## 入选文献

### 1. Dynamic functional connectivity in resting-state fMRI

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/22484408/
- 相关性评分：95
- 证据质量：high
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文6专门讨论了动态功能连接（Dynamic Functional Connectivity, dFC），这是功能连接分析领域一个重要的前沿和创新方向，提供了具体的分析方法（滑动窗口和状态空间方法）。
- 中文摘要压缩：动态功能连接（dFC）分析可以识别和表征随时间变化的连接模式。通过使用滑动窗口或基于状态的方法，可以研究大脑连接不是静态的，而是具有时间变化的特性。
- 主要贡献：提出了使用滑动窗口和状态空间方法来分析和表征时间变化的连接模式，为进行更精细、更动态的功能连接分析提供了理论和方法基础。
- 局限性：虽然提供了方法论，但没有具体指出在哪些类型的任务或疾病状态下进行dFC分析能产生最大的创新性，需要结合具体研究背景进行设计。

### 2. Complex brain networks: graph theoretical analysis of structural and functional systems

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/19895843/
- 相关性评分：90
- 证据质量：high
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文7介绍了图论（Graph Theory）在脑网络分析中的应用，这是从传统统计相关性分析向更复杂的网络拓扑结构分析转变的重大创新，是功能连接分析的进阶方向。
- 中文摘要压缩：图论为分析大脑网络提供了强大的工具，可以计算模块性（modularity）和效率（efficiency）等指标，从而全面描述整个大脑网络的组织结构和功能连接模式。
- 主要贡献：将图论理论引入脑网络分析，提供了一套系统性的指标（如模块性、效率）来量化和比较不同脑网络之间的组织结构和功能连接模式，提升了分析的深度和复杂性。
- 局限性：主要侧重于网络拓扑的描述性分析，对于如何将这些网络指标与特定的行为或病理机制进行因果性关联的指导性讨论较少。

### 3. A default mode of brain function

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/11209064/
- 相关性评分：85
- 证据质量：high
- 证据质量理由：功能连接分析通常围绕特定的网络（如默认模式网络DMN）展开。论文2介绍了DMN，它是功能连接分析中最核心、最常被研究的网络之一，是进行创新性功能连接研究的理想靶点。
- 中文摘要压缩：默认模式网络（DMN）是脑功能的一个基础目标网络，它在休息状态下活动，是进行休息态（rest-state）和任务态（task-state）神经科学研究的基石。
- 主要贡献：确定了DMN作为功能连接分析的经典且重要的研究靶点，为后续研究提供了明确的理论和网络基础。
- 局限性：内容较为基础和综述性，更多是确定了研究对象，而非提供具体的创新性分析方法。

### 4. Information-based functional brain mapping

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/16497565/
- 相关性评分：80
- 证据质量：medium
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文5介绍了基于信息论的脑图谱绘制（MVPA/解码），这代表了从简单的相关性分析到更高级的、基于信息编码的分析范式转变，具有很高的创新价值。
- 中文摘要压缩：基于信息论的脑图谱绘制（如MVPA/解码）旨在测试分布式活动模式是否携带特定的任务或条件信息，超越了简单的连接强度测量，关注信息编码的效率。
- 主要贡献：提出了从传统的连接强度分析转向基于信息论的分析范式，即测试大脑区域是否能够编码和解码特定的行为或认知信息，具有更高的机制解释力。
- 局限性：该方法需要高质量的、具有明确任务条件的任务态数据，且其信息量估计的计算复杂度和参数敏感性较高。

### 5. Mapping human brain networks with MEG and EEG

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/24174914/
- 相关性评分：75
- 证据质量：medium
- 证据质量理由：功能连接分析的创新性往往涉及模态的结合。论文11讨论了MEG和EEG，这两种电生理信号的连接分析（源定位和连接性分析）是功能连接分析的重要扩展和创新方向，提供了不同的时间分辨率和空间定位视角。
- 中文摘要压缩：结合MEG和EEG等电生理信号进行源定位和连接性分析，可以表征快速的神经通讯过程，提供了比fMRI更高的时空分辨率来研究功能连接。
- 主要贡献：将功能连接分析从血氧水平依赖（BOLD）信号扩展到电生理信号（EEG/MEG），极大地提高了时间分辨率，使研究能够捕捉到更快速的神经动力学过程。
- 局限性：信号的源定位和连接性分析受限于电极放置和信号传播的复杂性，且与BOLD信号的机制差异需要明确区分。

### 6. Multimodal integration in neuroimaging and neuroscience

- 年份/期刊： / 
- 作者：
- 来源：curated_seed
- URL：https://pubmed.ncbi.nlm.nih.gov/23298758/
- 相关性评分：70
- 证据质量：medium
- 证据质量理由：用户任务是进行功能连接分析的创新性实验。论文19讨论了多模态整合，这是当前神经科学研究的最高趋势之一。将功能连接分析与其他模态（如结构连接、代谢、基因表达）结合，是实现机制解释的创新路径。
- 中文摘要压缩：多模态整合是指结合多种不同的神经影像学和生物学模态（如功能、结构、代谢、转录组）数据，以提高对神经机制的解释力，使每个模态提供互补的约束。
- 主要贡献：指导研究者将功能连接分析结果与其他生物学或物理学模态（如结构连接组、代谢图谱）进行整合，从单纯的关联性分析提升到机制性、多层次的理解。
- 局限性：模态间的数据异质性（heterogeneity）和尺度差异巨大，如何建立可靠的跨模态关联模型是最大的技术挑战。

### 7. Functional connectivity in the motor cortex of resting human brain using echo-planar MRI

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

### 8. Amplitude of low-frequency fluctuation and fractional ALFF in resting-state fMRI

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

### 9. Statistical parametric maps in functional imaging

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
