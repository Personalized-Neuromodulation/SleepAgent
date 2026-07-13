function out=fmask(fdata,mask)
temp=squeeze(fdata(:,:,:,1));
if ~isequal(size(temp), size(mask))
    error('mask size is not equal to data size');
end
idx=find(mask>0);
fdata_reshape=reshape(fdata,[],size(fdata,4));
out=fdata_reshape(idx,:);
end



% import numpy as np

% def fmask(fdata, mask):
%     temp = np.squeeze(fdata[:,:,:,0])
%     if temp.shape != mask.shape:
%         raise ValueError('mask size is not equal to data size')
%     idx = np.where(mask > 0)
%     fdata_reshape = np.reshape(fdata, (-1, fdata.shape[3]))
%     out = fdata_reshape[idx,:]
%     return out