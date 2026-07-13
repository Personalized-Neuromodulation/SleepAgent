# 代码映射

- `run_init_bids.py`：初始化 BIDS 根目录、sourcedata、derivatives、fMRIPrep 输出目录和 `dataset_description.json`。
- `MRIAverageFactory.dcm2nii()`：对 DICOM 序列调用 `dcm2niix`。
- `MRIAverageFactory.mri_copy_nii_json()`：复制 NIfTI/JSON 到 BIDS 文件名。
- `fMRIPath.get_mri_anat_nii()`、`get_mri_func_nii()`：生成 anat/func BIDS 输入输出路径。
