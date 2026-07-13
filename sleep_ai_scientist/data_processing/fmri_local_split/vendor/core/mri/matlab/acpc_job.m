function acpc_job(f, i, j, k)
    matlabbatch = acpc(f, i, j, k);
    spm('defaults', 'PET');
    spm_jobman('run', matlabbatch);
end

function matlabbatch = acpc(f, i, j, k)
    nii = strcat(f, ',1')
    i = -str2double(i)
    j = -str2double(j)
    k = -str2double(k)
    matlabbatch{1}.spm.util.reorient.srcfiles = {
        strcat(f, ',1');
        };
    matlabbatch{1}.spm.util.reorient.transform.transprm = [i j k 0 0 0 1 1 1 0 0 0];
    matlabbatch{1}.spm.util.reorient.prefix = '';
end    
