# fmri_local_split

`fmri_local_split` 是从 `fmri_local` 拆出的可执行 skill 工程。入口不再把所有任务都落到统一 `analyze` 流程，而是根据用户任务选择阶段执行。

## 调度规则

- 用户明确说“完整分析 fmri 数据”“全流程”“端到端”时，执行完整流程。
- 用户没有给出明确局部任务时，默认执行完整流程。
- 用户只提到某个局部任务时，只执行对应阶段。

阶段顺序：

1. `fmri-bids-ingest`: 原始 DICOM 或已分类 DICOM/NIfTI 到 BIDS。
2. `fmri-fmriprep-qc`: 运行或复用 fMRIPrep，并整理 figures。
3. `fmri-denoise-regressors`: 生成回归器、去噪和去噪 carpetplot。
4. `fmri-surface-segment`: surface transform 和 sleep label 分段。
5. `fmri-timefreq-stats`: ALFF/fALFF、PSD 和 QC summary。

## 入口

```bash
python /home/zyb/Agent_skills/fmri_local_split/fmri_local_agent.py --help
```

示例：

```bash
python /home/zyb/Agent_skills/fmri_local_split/fmri_local_agent.py --input-root /data/fmri_agent/test_data/input --output-root /data/fmri_agent/test_data/output/multimodal_sleep_data --surface-mode 0 "完整分析fmri数据 sub-YZ1"

python /home/zyb/Agent_skills/fmri_local_split/fmri_local_agent.py --input-root /data/fmri_agent/test_data/input --output-root /data/fmri_agent/test_data/output/multimodal_sleep_data --surface-mode 0 "只对sub-YZ1执行segment分段"

python /home/zyb/Agent_skills/fmri_local_split/fmri_local_agent.py --input-root /data/fmri_agent/test_data/input --output-root /data/fmri_agent/test_data/output/multimodal_sleep_data --surface-mode 1 "只对sub-YZ1重新绘制去噪质控和时频统计"
```

## 原始 DICOM 输入

现在支持两类输入：

- 已整理输入：`sub-*/ses-mri*/anat|dwi|fmap|func/<series>/*.dcm` 或 NIfTI。
- 原始扫描导出：`sub-*/mri/<扫描日期或检查目录>/<series>/*.dcm`。

原始扫描导出会先整理到输出 BIDS 根目录的 `sourcedata`：

```text
<output-root>/
  dataset_description.json
  sourcedata/
    sub-ISM035/
      ses-mri0/
        anat/
        dwi/
        fmap/
        func/
      ses-mri1/
        anat/
        dwi/
        fmap/
        func/
  sub-ISM035/
    ses-mri0/
      anat/
      func/
  derivatives/
    sub-ISM035/
      fmriprep/
        output/
      ses-mri0/
      ses-mri1/

<output-root 的父目录>/
  work/
    <output-root 目录名>/
      sub-ISM035/
```

默认把第一个原始检查目录映射为 `ses-mri0`，第二个映射为 `ses-mri1`。可用 `FMRI_RAW_SESSION_START` 调整起始编号。DICOM 归档默认使用 hardlink，跨文件系统失败时自动复制；可用 `FMRI_SOURCEDATA_COPY_MODE=symlink|hardlink|copy|auto` 调整。

fMRIPrep 临时工作目录不放在 BIDS 根目录内。默认使用 `<output-root 的父目录>/work/<output-root 目录名>/<subject>`，例如 `/data/fmri_agent/work/multimodal_sleep_data/sub-ISM035`。可用 `FMRIPREP_WORK_DIR=/path/to/work_root` 覆盖 work 根目录。

## 实验目录批处理

当输入目录本身是一个实验目录，例如：

```text
fmri_data/JingZongOLT/
  sub-ISM035/
  sub-ISM036/
```

用户输入保存目录 `fmri_result` 时，输出会自动改名为 `multimodal_sleep_data`，BIDS 层级位于 `bids` 子目录，agent 日志位于同级 `agent_log`：

```text
multimodal_sleep_data/
  bids/
    sourcedata/
    sub-*/
    derivatives/
      FMRIPREP/
        sub-*/
  agent_log/
    <timestamp>/
```

当输入目录是多个实验的父目录，例如：

```text
fmri_data/
  JingZongOLT/
  YangZhiHC/
  YangZhiOLT/
```

Agent 会识别每个实验目录，并按顺序处理，但所有实验共用同一个输出 BIDS 根目录，不再按实验名创建 `JingZongOLT/fmri_free` 这类分层：

```text
multimodal_sleep_data/
  bids/
    sourcedata/
    sub-*/
    derivatives/FMRIPREP/sub-*/
  agent_log/<timestamp>/
```

如果用户 prompt 中只点名部分实验，例如 `只处理 JingZongOLT 和 YangZhiHC`，LLM 解析出的 `experiments` 会用于筛选并保持用户指定顺序。

也可以直接调用单个 stage：

```bash
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py segment
python /home/zyb/Agent_skills/fmri_local_split/agent_skills/fmri-pipeline/scripts/fmri_pipeline.py timefreq
```

## 保留的 Python 文件

当前只保留执行链需要的 Python 文件：入口 agent、pipeline dispatcher、5 个 stage runner、FastSurfer runner、`run_layered_skill_analysis.py` 共享函数库、两个 fMRIPrep runner 和 `split_stage_utils.py`。
