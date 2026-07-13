function nuisance_regressout_volume(img_path, regressor_path, clean_data_path)
	ori_img = load_untouch_nii(img_path);
	img_data = ori_img.img;
	load(regressor_path);
	Multi_Regessor = [ones(size(score,1),1), score];

	clean = reshape(img_data, [], size(img_data, 4));
	% ori = reshape(img_data, [], size(img_data, 4));
	clean = double(clean);

	for iii = 1:size(clean,1)
		[Beta,~,Residual] = regress(squeeze(clean(iii,:))',Multi_Regessor);
		clean(iii,:) = Residual + Beta(1);
	end
	clean_img = reshape(clean, size(img_data));
	ori_img.img = clean_img;
	save_untouch_nii(ori_img, clean_data_path);
end



% function nuisance_regressout_volume(img_path, regressor_path, clean_data_path)	
% 	mask_path =  '/home/poolab/HDD/data/ISM_HC_Patient/derivatives/FMRIPREP/sub-ISM2/ses-mri0/func/sub-ISM2_ses-mri0_task-sleep_space-T1w_desc-brain_mask.nii.gz';
% 	clean_data_path = '/mnt/nas/Projects/smhc_sleep/ISM_HC_Patient/derivatives/FMRIPREP/sub-ISM2/ses-mri0/clean_data/volume/sub-ISM2_ses-mri0_task-sleep_space-T1w_desc-preproc_bold_12rp_csf_wm.nii.gz';
% 	ori_img = load_nii(img_path);
% 	img_data = double(ori_img.img);
    
%     mask = load_nii(mask_path);
%     mask_data = logical(mask.img);
    
%     % img_mask_data = img_data(mask_data);
% %     img_mask_data = normalize(img_mask_data);
%     global_mean_intensity = mean(img_data(mask_data));
%     normalized_data_time_course = (img_data / global_mean_intensity) * 100;
    
    
% 	load(regressor_path);
% 	Multi_Regessor = [ones(size(score,1),1), score];

% 	clean = reshape(normalized_data_time_course, [], size(normalized_data_time_course, 4));
% 	% ori = reshape(img_data, [], size(img_data, 4));
% 	clean = double(clean);

% 	for iii = 1:size(clean,1)
% 		[Beta,~,Residual] = regress(squeeze(clean(iii,:))',Multi_Regessor);
% 		clean(iii,:) = Residual + Beta(1);
% 	end
% 	clean_img = reshape(clean, size(img_data));
% %     clean_img = clean_img/ max(abs(clean_img(:))) * 100;
% 	ori_img.img = single(clean_img);
% 	save_untouch_nii(ori_img, clean_data_path);

%     % save_nii(ori_img,clean_data_path);

% 	% niftiwrite(ori_img.img, clean_data_path,'Compressed', true );

% end
