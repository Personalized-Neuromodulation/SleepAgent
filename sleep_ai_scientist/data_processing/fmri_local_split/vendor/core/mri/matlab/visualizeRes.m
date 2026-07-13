function visualizeRes(P1)
% visualizeRes(P1,P2,T2,node,elem,face,inCurrent,hdrInfo,uniTag,showAll,varargin)
%
% Display the simulation results. The 3D rendering is displayed in the
% world space, while the slice view is done in the voxel space.
%
% (c) Yu (Andy) Huang, Parra Lab at CCNY
% yhuang16@citymail.cuny.edu
% April 2018
% August 2019 callable by roast_target()

[dirname,baseFilename] = fileparts(P1);

data = load_untouch_nii([dirname filesep 'masks.nii']);
load(fullfile(dirname,'mesh.mat'));
for i = 1:3
    node(:,i) = node(:,i) + data.hdr.hist.(['qoffset_' 'x'+i-1]);
end

indNode_grayFace = face(find(face(:,4) == 2),1:3);
indNode_grayElm = elem(find(elem(:,5) == 2),1:4);
    
fid = fopen([dirname filesep baseFilename '_e.pos']);
fgetl(fid);
C = textscan(fid,'%d %f %f %f');
fclose(fid);

% dataShow = [node(C{1},1:3), C_ef_mag];
color = nan(size(node,1),1);
color(C{1}) = sqrt(C{2}.^2+C{3}.^2+C{4}.^2);
dataShow = [node(:,1:3) color];

figure;
colormap(jet);
plotmesh(dataShow,indNode_grayFace,indNode_grayElm,'LineStyle','none');
dataShowRange = [min(dataShow(unique(indNode_grayElm(:)),4)) prctile(dataShow(unique(indNode_grayElm(:)),4),95)];

axis off; rotate3d on;
caxis(dataShowRange);
lightangle(-90,45)
lightangle(90,45)
lightangle(-90,-45)

end
