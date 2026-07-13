function spm_estimate(r, s)
    matlabbatch = est(r, s);
    spm('defaults', 'PET');
    spm_jobman('run', matlabbatch);
end

function matlabbatch = est(r, s)

	source_image = fullfile([s,',1'])
	ref_image = fullfile([r,',1'])
	matlabbatch{1}.spm.spatial.coreg.estimate.ref = {ref_image};
	matlabbatch{1}.spm.spatial.coreg.estimate.source = {source_image};
	matlabbatch{1}.spm.spatial.coreg.estimate.other = {''};
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.cost_fun = 'nmi';
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.sep = [4 2];
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.tol = [0.02 0.02 0.02 0.001 0.001 0.001 0.01 0.01 0.01 0.001 0.001 0.001];
	matlabbatch{1}.spm.spatial.coreg.estimate.eoptions.fwhm = [7 7];
end    
