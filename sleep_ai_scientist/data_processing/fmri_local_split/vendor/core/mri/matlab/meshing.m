function [elem,node] = meshing(fn, output)
% if isempty(dn), dn = pwd; end

% numOfTissue = 6; % hard coded across ROAST.  max(allMask(:));
nii = load_untouch_nii(fn);

allMask = uint8(zeros(size(nii.img)));

label = unique(nii.img); label(1) = [];

disp(length(label));
for i = 1:length(label)
    allMask(nii.img == label(i)) = i;
end

meshOpt = struct('radbound',2,'angbound',10,'distbound',0.3,'reratio',2,'maxvol',2);

% opt.radbound = 5; % default 6, maximum surface element size
% opt.angbound = 30; % default 30, miminum angle of a surface triangle
% opt.distbound = 0.4; % default 0.5, maximum distance
% % between the center of the surface bounding circle and center of the element bounding sphere
% opt.reratio = 3; % default 3, maximum radius-edge ratio
% maxvol = 10; %100; % target maximum tetrahedral elem volume

[node,elem,face] = cgalv2m(allMask,meshOpt,meshOpt.maxvol);

% node(:,1:3) = node(:,1:3) + 0.5; % then voxel space
% 
% for i = 1:3
%     node(:,i) = node(:,i)*nii.hdr.dime.pixdim(1+i);
% end
% save('mesh_befor_fix.mat','elem','face');

[node_fix,elem_fix]=meshcheckrepair(node,elem,'isolated');
% [node,elem]=meshcheckrepair(node,elem,'isolated');

% save('mesh_parcell.mat','elem','face');
% 
% elem(elem(:,end)>length(label(label<1000)),end) = 2;
% face(face(:,end)>length(label(label<1000)),end) = 2;

disp('saving mesh...')

% savemsh(node(:,1:3),elem, 'pp6_ori.msh');
savemsh(node_fix(:,1:3),elem_fix, output);
% save([subj'.mat'],'node','elem','face');
end