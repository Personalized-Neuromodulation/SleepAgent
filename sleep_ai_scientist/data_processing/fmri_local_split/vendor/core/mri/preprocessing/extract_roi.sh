for arg in "$@"
do
  case "$arg" in
  -t1)
   t1=$2
   shift;shift
  ;;
  -t2)
   t2=$2
   shift;shift
  ;;
   esac
done


VOXSIZE=1
STD_MNI=$FSLDIR/data/standard/MNI152_T1_1mm.nii.gz

fslswapdim $t1 x -z y tmpImg
mri_convert -cs $VOXSIZE tmpImg.nii.gz tmpImg.nii.gz
mri_convert -cm tmpImg.nii.gz tmpImg.nii.gz
df_conf=`fslval tmpImg dim1`
rm tmpImg.nii.gz

fslswapdim $t1 x -z y tmpImg
mri_convert -nc -cs $VOXSIZE -oni $df_conf -onj $df_conf -onk $df_conf -rt cubic tmpImg.nii.gz T1fs_resamp.nii.gz
fslswapdim T1fs_resamp x z -y T1fs_resamp
rm tmpImg.nii.gz

offset_x=`expr $VOXSIZE \* $df_conf / 2`
offset_y=`expr -$VOXSIZE \* $df_conf / 2`
offset_z=`expr -$VOXSIZE \* $df_conf / 2 + $VOXSIZE`
fslorient -setqform -$VOXSIZE 0 0 $offset_x 0 $VOXSIZE 0 $offset_y 0 0 $VOXSIZE $offset_z 0 0 0 1 T1fs_resamp
fslorient -setsform -$VOXSIZE 0 0 $offset_x 0 $VOXSIZE 0 $offset_y 0 0 $VOXSIZE $offset_z 0 0 0 1 T1fs_resamp

flirt -in $STD_MNI -ref T1fs_resamp -out MNIfs_reg
var=`fslstats MNIfs_reg -w`
zmin=`echo $var | awk '{print $5}'`
zsize=$(expr $df_conf - $zmin)

fslroi T1fs_resamp T1fs_roi 0 -1 0 -1 $zmin $zsize
fslcreatehd $df_conf $df_conf $zmin 1 $VOXSIZE $VOXSIZE $VOXSIZE 1 0 0 0 16 tmpImg
fslmerge -z T1fs_roi tmpImg T1fs_roi
rm tmpImg.nii.gz
fslcpgeom T1fs_resamp T1fs_roi
fslswapdim T1fs_roi x -z y T1fs_roi_FS
rm MNIfs_reg.nii.gz
rm T1fs_resamp.nii.gz
rm T1fs_roi.nii.gz

flirt -in $STD_MNI -ref $t2 -out MNIfs_regT2
var=`fslstats MNIfs_regT2 -w`
zmin=`echo $var | awk '{print $5}'`
zsize=`echo $var | awk '{print $6}'`

df1=`fslval $t2 dim1`
df2=`fslval $t2 dim2`

fslroi $t2 T2_roi 0 $df1 0 $df2 $zmin $zsize
rm MNIfs_regT2.nii.gz
	  
rm $t1.nii.gz
rm $t2.nii.gz
mv T1fs_roi_FS.nii.gz $t1.nii.gz
mv T2_roi.nii.gz $t2.nii.gz	   
	  
