function n_PCA = pca_volume(img_path, mask_path, output_path, n_PCA, intensity_threshold, explained_ratio)
	ori_img = load_untouch_nii(img_path);
    	fmri = ori_img.img;
    	mask_img = load_untouch_nii(mask_path);
    	lmask = mask_img.img;

	lmask = abs(1-lmask);
	SE = strel('square',3);
	mask_RAM = reshape(lmask,[size(lmask,1) size(lmask,2)*size(lmask,3)]);
	mask_RAM =  imerode(mask_RAM,SE);
	mask_RAM = reshape(mask_RAM,size(lmask));
	
	fMRI_noise = fmask(fmri, mask_RAM);
	fMRI_noise(isnan(fMRI_noise)) = 0;
	fMRI_intensity = mean(fMRI_noise,2);
	fMRI_intensity_descend = sort(fMRI_intensity,'descend');

	% thr = fMRI_intensity>=fMRI_intensity_descend(floor(numel(fMRI_intensity)*0.005));
	% thr_idx = find(thr>0);
	% fMRI_noise = fMRI_noise(thr_idx, :);
	% fMRI_noise = double(fMRI_noise);
	
	lmask = zeros(size(lmask));
    lmask(fMRI_intensity>=fMRI_intensity_descend(floor(numel(fMRI_intensity)*intensity_threshold))) = 1;
    fMRI_noise = double(fmask(fmri,lmask));

	% if std(fMRI_noise,0,2) == 0
	fMRI_noise_ready_PCA = (fMRI_noise-mean(fMRI_noise,2))./ (std(fMRI_noise,0,2) + 0.0001);
	% else
		% fMRI_noise_ready_PCA = (fMRI_noise-mean(fMRI_noise,2))./ (std(fMRI_noise,0,2));
	% end
		
	% stage 02 : principle component analysis
	[coeff,score,latent,tsquared,explained,mu]= pca(fMRI_noise_ready_PCA','algorithm','svd');
	if n_PCA == 0
		for j = 1:size(explained,1)
			total = sum(explained(1:j));
			if total > explained_ratio
				n_PCA = j;
				break
			end
		end
	end
    % disp(n_PCA);
	score = score(:, 1:n_PCA);
	save(output_path, 'score');
end



% import numpy as np
% import nibabel as nib
% from scipy.ndimage import morphology

% def pca_volume(img_path, mask_path, output_path, n_PCA, intensity_threshold):
    % ori_img = nib.load(img_path)
    % fmri = ori_img.get_fdata()
    % mask_img = nib.load(mask_path)
    % lmask = mask_img.get_fdata()
    % lmask = np.abs(1 - lmask)
    % SE = morphology.generate_binary_structure(3, 1)
    % mask_RAM = np.reshape(lmask, [lmask.shape[0], lmask.shape[1]*lmask.shape[2]])
    % mask_RAM = morphology.binary_erosion(mask_RAM, SE)
    % mask_RAM = np.reshape(mask_RAM, lmask.shape)
    % fMRI_noise = fmri * mask_RAM
    % fMRI_noise[np.isnan(fMRI_noise)] = 0
    % fMRI_intensity = np.mean(fMRI_noise, axis=1)
    % fMRI_intensity_descend = np.sort(fMRI_intensity)[::-1]
    % lmask = np.zeros(lmask.shape)
    % lmask[fMRI_intensity >= fMRI_intensity_descend[int(np.floor(len(fMRI_intensity)*0.005))]] = 1
    % fMRI_noise = fmri * lmask
    % if np.std(fMRI_noise, axis=1) == 0:
    %     fMRI_noise_ready_PCA = (fMRI_noise - np.mean(fMRI_noise, axis=1)) / (np.std(fMRI_noise, axis=1) + 0.0001)
    % else:
    %     fMRI_noise_ready_PCA = (fMRI_noise - np.mean(fMRI_noise, axis=1)) / np.std(fMRI_noise, axis=1)
    % coeff, score, latent, tsquared, explained, mu = np.linalg.svd(fMRI_noise_ready_PCA.T)
    % score = score[:, :n_PCA]
    % np.save(output_path, score)

