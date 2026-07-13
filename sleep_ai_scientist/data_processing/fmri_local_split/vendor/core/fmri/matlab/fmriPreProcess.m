% clear; clc;
% The toolbox was created at Laureate Institute for Brain Research 
% For technical issues, code and bugs please contact Obada Al Zoubi
% obada.y.alzoubi@gmail.com
% For sharing and general questions, please contact Dr. Jerzy Bodurka,
% Laureate Institute for Brain Research 
% This script is demo for running APPEAR Toolbox 


% addpath('funcs');
% % addpath('eeglab2019_0');
% [ALLEEG, ~, ~, ~] = eeglab;
% close all;
% clear;
% clc;

% subjects = {'ISM_008', 'ISM_010', 'ISM_011', 'ISM_012', 'ISM_013'};
% subjects_name = {'ISM_008_2', 'ISM_010_2', 'ISM_011_2', 'ISM_012_2', 'ISM_013_2'};
% % orig_data_dir = '\\172.16.6.4\lglab\Projects\smhc_sleep\ISM';
% % subject_out_dir = '\\172.16.6.4\lglab\Projects\smhc_sleep\ISM_Process';

% orig_data_dir = 'G:\lg\project_data\smhc\ISM';
% subject_out_dir = 'G:\lg\project_data\smhc\ISM_Process';

% % orig_data_dir = 'G:\lg\project_data\smhc\ISM_HC';
% % subject_out_dir = 'G:\lg\project_data\smhc\ISM_HC_Process';
% n_scans = ['1', '1', '1', '1', '1'];

% for i=1:length(subjects)
%     subject = char(subjects(i));
%     subj_out_dir = [subject_out_dir filesep subject filesep 'eeg_fmri' filesep n_scans(i) filesep 'clean_eeg_fmri' filesep 'clean_data_aapear'];
%     mkdir([subject_out_dir filesep subject filesep 'eeg_fmri' filesep n_scans(i)]);
%     mkdir([subject_out_dir filesep subject filesep 'eeg_fmri' filesep n_scans(i) filesep 'clean_eeg_fmri']);
%     mkdir(subj_out_dir);
    
%     subj_name = char(subjects_name(i));
% %     subj_name = subject;
%     sub_folder = [orig_data_dir filesep subject filesep 'eeg_fmri' filesep n_scans(i)];
    
% %     subj_name_temp = split(subj_name, 'HC');
% %     subj_eeg_file = strcat(subj_name_temp{2,1}, '.vhdr');
%     subj_eeg_file = strcat(subj_name, '.vhdr');
% %     subj_out_folder = [subj_out_dir filesep subj_name];
%     subj_out_folder = subj_out_dir;
% %     mkdir(subj_out_folder);
    
%     %% Add required paths and functions 

% %     sub_folder     ='D:\lg\project_data\smhc\ISM_HC\ISM_HC006\fmri_eeg';
%     % data are in brain vision analyzer format 
% %     subj_eeg_file  = '006.vhdr'; 

%     subj_ecg_file = '';

%     %% Output folder 

% %     subj_out_folder = 'D:\lg\project_data\smhc\ISM_HC_Process\eeg_fmri\clean_eeg_fmri\clean_data_aapear';

%     %% Store Configuration in EEG.APPEAR

%     TR              = 2;% seconds
%     slice_per_TR    = 33; % slices per volume 
%     scntme          = 1200*2; % Scan length in secs
%     slice_mk_path   = [orig_data_dir filesep subject filesep 'eeg_fmri' filesep n_scans(i) filesep strcat(subj_name,'.mat')];
% %     bad_chs         = {'F4',};
%     bad_chs         = {};
%     ECG_ch_ind      = 32 - length(bad_chs);

    
%     %% Read EEG, channel names and Slice Markers (R128) 

function fmriPreProcess(vhdr_path, subj_out_folder, slice_mk_path, subj_ecg_file, scntme, TR, slice_per_TR, bad_chs, suffix)
    if isempty(bad_chs)
        bad_chs = {};
    else
        bad_chs = cellstr(bad_chs);  
    end
    
    [sub_folder, subj_name] = fileparts(vhdr_path);
    subj_vhdr_file = strcat(subj_name, '.vhdr');
    ECG_ch_ind = 32 - length(bad_chs);
    % Step 1
    [EEG] = load_EEG(sub_folder, subj_vhdr_file, scntme, TR, slice_per_TR, slice_mk_path, bad_chs);
    % Set channel locations 
    chanlocs                         = loadbvef('BC-MR-32.bvef');
    chanlocs(1:2)                    = []; % Get rid of GND and REF
    ch_all                           = chanlocs(1:end-1); % get rid of ECG
    index = 1;
    while index <= length(chanlocs)
        for bad_chan_index=1:length(bad_chs)
            if strcmp(chanlocs(index).labels, char(bad_chs(bad_chan_index)))
                chanlocs(index) = [];
                index = index - 1;
                break
            end
        end
        index = index + 1;
    end
    
    
    EEG.chanlocs                     = chanlocs;

    EEG.APPEAR.Fs                    = 250;% Hz frequency of the EEG output 
    EEG.APPEAR.filterRange           = [0.35 70]; %Hz - filter output EEG between 1 and 70 Hx
    EEG.APPEAR.BCG_Crorrection       = 'fMRIB'; % Recommended
%     EEG.APPEAR.BCG_Crorrection       = 'MSPD'; % 
    EEG.APPEAR.ECG_ch_ind            = ECG_ch_ind; % ECG index (channel # 32)
    EEG.APPEAR.polt_ecg_range        = 5:35 ;% For QA, plot 30 sec of ECG waveform and the detected Peaks.

    %% If we want to use Pulse Ox for BCG correction, add required fields  
   
    % Step 2 
    if ~isempty(subj_ecg_file) && strcmp(EEG.APPEAR.BCG_Crorrection, 'Pulse_Ox')
        % Read and resmaple Pulse Ox., then detect R peaks 
        [Peak_locations, pusleox_waveform]  = pulseOx_DetectPeaks(strcat(sub_folder, subj_ecg_file),...
          EEG.APPEAR.PulseOx_Fs  , EEG.APPEAR.Fs, EEG.APPEAR.PulseOX.minHearteRate) ;
       % Save QRS peaks, Fs and waveform  
        EEG.APPEAR.PulseOX.Peaks     = Peak_locations;
        EEG.APPEAR.PulseOX.Fs        = EEG.APPEAR.Fs;
        EEG.APPEAR.PulseOX.waveform  = pusleox_waveform ;

    end

    %% Run APPEAR 
%       EEG2 = APPEAR(EEG, subj_out_folder, subj_name_temp{2,1});
    EEG2 = APPEAR(EEG, subj_out_folder, suffix);
    EEG2.chanlocs(end) = [];
    EEG2.icachansind = [1:size(EEG2.data, 1)];
    EEG2 = pop_interp(EEG2, ch_all, 'spherical');
    
    %% Output APPEAR to a file 
    suffix ='final';
    % Save final EEG
    corrEEG_filename = fullfile(subj_out_folder, strcat(suffix, '_', 'eeg_p-2'));
    
    % strcat(subj_out_folder, '/', suffix, '_', 'eeg_p-2');
    % As edf
    pop_writebva(EEG2,corrEEG_filename);
%     % as MAT
%     save(strcat(corrEEG_filename, '.mat'),'EEG2');
%     % As CSV
%     csvwrite(strcat(corrEEG_filename, '.csv'),EEG2.data );
end