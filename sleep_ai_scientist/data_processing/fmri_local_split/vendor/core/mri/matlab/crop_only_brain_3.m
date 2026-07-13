%%%Crop the image using FOV and brain size
function image_crop=crop_only_brain_3(nii,outname)
        %%% nii. after crop
        %%% outname of .txt with coords
        
        nii_in=([nii]);
        crop_out=([outname]);
        nii=load_nifti(nii_in);


        voxel_size_x=nii.pixdim(2,1);
        voxel_size_y=nii.pixdim(3,1);
        voxel_size_z=nii.pixdim(4,1);

        fov_size=size(nii.vol);

        fov_x=round(fov_size(1,1)/2);
        fov_y=round(fov_size(1,2)/2);
        fov_z=round(fov_size(1,3)/2);

        X_dim=round(67/voxel_size_x); %65 mm max size monkey brain %calculate the slices number
        Y_dim=round(89/voxel_size_y); %75 mm max size monkey brain
        Z_dim=round(62/voxel_size_z); %55 mm max size monkey brain

        center_image=[fov_x,fov_y,fov_z];

        axis_x_start=round((X_dim/2)+center_image(1,1));
        axis_x_end=round(center_image(1,1)-(X_dim/2));

        axis_y_start=round((Y_dim/2)+center_image(1,2));
        axis_y_end=round(center_image(1,2)-(Y_dim/2));

        axis_z_start=round((Z_dim/2)+center_image(1,3));
        axis_z_end=round(center_image(1,3)-(Z_dim/2));


        if  axis_x_end <= 0 || axis_x_start >= fov_size (1,1)
            if axis_y_end > 0
                axis_y=[axis_y_end,axis_y_start];
                axis_z=[axis_z_end,axis_z_start];

                axis_y=[num2str(axis_y_end), ':', num2str(axis_y_start)];
                axis_z=[num2str(axis_z_end), ':', num2str(axis_z_start)];

                image_crop=['-axis 1 ', axis_y];
                image_crop=[image_crop,' -axis 2 ',axis_z];
                s=''''
                eval([ 'dlmwrite(' s crop_out s ',image_crop,' s 'delimiter' s ',' s '' '' s ')' ])    
            end
        end
            
        if axis_x_end > 0 && axis_x_start < fov_size (1,1)
            if axis_y_end > 0
               axis_x=[axis_x_end,axis_x_start];
               axis_y=[axis_y_end,axis_y_start];
               axis_z=[axis_z_end,axis_z_start];

               axis_x=[num2str(axis_x_end), ':', num2str(axis_x_start)];
               axis_y=[num2str(axis_y_end), ':', num2str(axis_y_start)];
               axis_z=[num2str(axis_z_end), ':', num2str(axis_z_start)];

               image_crop=['-axis 0 ',axis_x ];
               image_crop=[image_crop,' -axis 1 ', axis_y];
               image_crop=[image_crop,' -axis 2 ',axis_z];
               s=''''
               eval([ 'dlmwrite(' s crop_out s ',image_crop,' s 'delimiter' s ',' s '' '' s ')' ])
            end
        end
        
        if  axis_z_end <= 0 || axis_z_start >= fov_size (1,3)
            if axis_y_end > 0
               axis_x=[axis_x_end,axis_x_start];
               axis_y=[axis_y_end,axis_y_start];

               axis_x=[num2str(axis_x_end), ':', num2str(axis_x_start)];
               axis_y=[num2str(axis_y_end), ':', num2str(axis_y_start)];

               image_crop=['-axis 0 ', axis_x];
               image_crop=[image_crop,' -axis 1 ',axis_y];
               s=''''
               eval([ 'dlmwrite(' s crop_out s ',image_crop,' s 'delimiter' s ',' s '' '' s ')' ])
            end
        end
        
        if axis_x_end <= 0 || axis_x_start >= fov_size (1,1)
            if axis_y_end > 0
                 if axis_z_end <= 0 || axis_z_start >= fov_size (1,3)
                    axis_y=[axis_y_end,axis_y_start];
                    
                    axis_y=[num2str(axis_y_end), ':', num2str(axis_y_start)];
                    image_crop=['-axis 1 ', axis_y];
                    s=''''
                    eval([ 'dlmwrite(' s crop_out s ',image_crop,' s 'delimiter' s ',' s '' '' s ')' ])
                 end
            end
        end
        
        if axis_y_end <= 0 || axis_y_start >= fov_size (1,2)
               if axis_x_end <= 0 || axis_x_start >= fov_size (1,1)
                    axis_z=[axis_z_end,axis_z_start];
                    
                    axis_z=[num2str(axis_z_end), ':', num2str(axis_z_start)];
                    image_crop=['-axis 2 ', axis_z];
                    s=''''
                    eval([ 'dlmwrite(' s crop_out s ',image_crop,' s 'delimiter' s ',' s '' '' s ')' ])
               end
        end
        
        if axis_x_end <= 0 && axis_y_end <= 0 && axis_z_end <= 0
               fov_size(1,1)=fov_size(1,1)-1;
               fov_size(1,2)=fov_size(1,2)-1;
               fov_size(1,3)=fov_size(1,3)-1;

               axis_x=[0,(fov_size(1,1)-1)];
               axis_y=[0,fov_size(1,2)];
               axis_z=[0,fov_size(1,3)];

               axis_x=[num2str(0), ':', num2str((fov_size(1,1)-1))];
               axis_y=[num2str(0), ':', num2str(fov_size(1,2))];
               axis_z=[num2str(0), ':', num2str(fov_size(1,3))];

               image_crop=['-axis 0 ', axis_x];
               image_crop=[image_crop,' -axis 1 ',axis_y];
               image_crop=[image_crop,' -axis 2 ',axis_z];

               s='''';
               eval([ 'dlmwrite(' s crop_out s ',image_crop,' s 'delimiter' s ',' s '' '' s ')' ])
        end 
        image_crop=0;
end
