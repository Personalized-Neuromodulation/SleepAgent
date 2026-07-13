function ct_job(dn)
    matlabbatch = ct(dn);
    spm('defaults', 'PET');
    spm_jobman('run', matlabbatch);
end

function matlabbatch = ct(dn)

	source_image = fullfile(dn, 'simu/CT.nii,1')
	ref_image = fullfile(dn, 'T1.nii,1')
	matlabbatch{1}.spm.spatial.coreg.estimate.ref = {ref_image};
	matlabbatch{1}.spm.spatial.coreg.estimate.source = {source_image};
	matlabbatch{1}.spm.spatial.coreg.estimate.other = {''};
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.cost_fun = 'nmi';
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.sep = [4 2];
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.tol = [0.02 0.02 0.02 0.001 0.001 0.001 0.01 0.01 0.01 0.001 0.001 0.001];
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.fwhm = [7 7];
end    
