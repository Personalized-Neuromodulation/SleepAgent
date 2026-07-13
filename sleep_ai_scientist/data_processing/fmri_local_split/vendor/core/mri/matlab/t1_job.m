function t1_job(dn)
    matlabbatch = t1(dn);
    spm('defaults', 'PET');
    spm_jobman('run', matlabbatch);
end

function matlabbatch = t1(dn)

	source_image = fullfile(dn, 'T1.nii,1')
	ref_image = fullfile(dn, 'conform_acpc.nii,1')
	matlabbatch{1}.spm.spatial.coreg.estimate.ref = {ref_image};
	matlabbatch{1}.spm.spatial.coreg.estimate.source = {source_image};
	matlabbatch{1}.spm.spatial.coreg.estimate.other = {''};
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.cost_fun = 'nmi';
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.sep = [4 2];
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.tol = [0.02 0.02 0.02 0.001 0.001 0.001 0.01 0.01 0.01 0.001 0.001 0.001];
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.fwhm = [7 7];
end    
