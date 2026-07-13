
function reslice_job(r, s)
    matlabbatch = reslice(r, s);
    spm('defaults', 'PET');
    spm_jobman('run', matlabbatch);
end

function matlabbatch = reslice(r, s)
	source_image = fullfile([s,',1'])
	ref_image = fullfile([r,',1'])
	matlabbatch{1}.spm.spatial.coreg.write.ref = {ref_image};
	matlabbatch{1}.spm.spatial.coreg.write.source = {source_image};
	matlabbatch{1}.spm.spatial.coreg.write.roptions.interp = 4;
	matlabbatch{1}.spm.spatial.coreg.write.roptions.wrap = [0 0 0];
	matlabbatch{1}.spm.spatial.coreg.write.roptions.mask = 0;
	matlabbatch{1}.spm.spatial.coreg.write.roptions.prefix = 'reslice_';
	
end    
