function padding(dn, seg, outfile)


T1 = load_untouch_nii(fullfile(dn,'T1_padding.nii'));
seg = load_untouch_nii(fullfile(dn, seg));
img = seg.img;
szo = size(img);
sz = size(img);
img = cat(1,single(zeros(.25*sz(1),sz(2),sz(3))),img,single(zeros(.25*sz(1),sz(2),sz(3))));
sz = size(img);
img = cat(2,img,single(zeros(sz(1),.5*sz(2),sz(3))));
sz = size(img);
img = cat(3,single(zeros(sz(1),sz(2),.5*sz(3))),img);
T1.img = img;
save_untouch_nii(T1,fullfile(dn, outfile));


end
