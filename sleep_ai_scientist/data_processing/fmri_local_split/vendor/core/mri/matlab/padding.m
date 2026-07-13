function padding(dn, filename)

T1 = load_untouch_nii(fullfile(dn,filename));

img = T1.img;

szo = size(img);

sz = size(img);
img = cat(1,single(zeros(.25*sz(1),sz(2),sz(3))),img,single(zeros(.25*sz(1),sz(2),sz(3))));

sz = size(img);
img = cat(2,img,single(zeros(sz(1),.5*sz(2),sz(3))));

sz = size(img);
img = cat(3,single(zeros(sz(1),sz(2),.5*sz(3))),img);

A = [T1.hdr.hist.srow_x;T1.hdr.hist.srow_y;T1.hdr.hist.srow_z;0 0 0 1];
S = [1 0 0 .25*szo(1);0 1 0 0;0 0 1 .5*szo(3);0 0 0 1];
A1 = A / S;

T1.hdr.hist.srow_x = A1(1,:);
T1.hdr.hist.srow_y = A1(2,:);
T1.hdr.hist.srow_z = A1(3,:);
T1.hdr.hist.qoffset_x = A1(1,4);
T1.hdr.hist.qoffset_y = A1(2,4);
T1.hdr.hist.qoffset_z = A1(3,4);

T1.img = img;
T1.hdr.dime.dim(2:4) = size(img);

save_untouch_nii(T1,fullfile(dn,'T1_padding.nii'));
lpz_updateQPara(fullfile(dn,'T1_padding.nii'));




end
