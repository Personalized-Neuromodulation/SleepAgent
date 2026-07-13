function lpz_updateQPara(fp_nii)
%
% If reorient the coordinate system of nii file by SPM, srow parameters will be
% corrected but not Q parameters, which may make errors in some other MRI
% processing toolboxes or softwares. This function is to fix this problem.
%
% inputs
% fp_nii: path of nii file
%
% Created by lipzh@shanghaitech.edu.cn on 2021-09-27

nii = load_untouch_nii(fp_nii);

M_affine = [nii.hdr.hist.srow_x; nii.hdr.hist.srow_y; nii.hdr.hist.srow_z];
resolution = nii.hdr.dime.pixdim(2:4); 
M_rotate = eye(3);
for ii = 1:3
    M_rotate(:,ii) = M_affine(:,ii)/resolution(ii);
end

quat = dcm2quat(M_rotate);
if sum(sign(quat(2:end)))<0
    quat = -quat;
end
nii.hdr.hist.quatern_b = quat(2);
nii.hdr.hist.quatern_c = quat(3);
nii.hdr.hist.quatern_d = quat(4);

nii.hdr.hist.qoffset_x = nii.hdr.hist.srow_x(4);
nii.hdr.hist.qoffset_y = nii.hdr.hist.srow_y(4);
nii.hdr.hist.qoffset_z = nii.hdr.hist.srow_z(4); % update header

save_untouch_nii(nii,fp_nii);
end