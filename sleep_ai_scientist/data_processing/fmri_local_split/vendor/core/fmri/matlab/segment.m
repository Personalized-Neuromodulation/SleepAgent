function tdcs_segment(vhdr_path, process_dir, eeg_detail)
    
    [sub_folder, subj_name] = fileparts(vhdr_path);
    subj_vhdr_file = strcat(subj_name, '.vhdr');
    eeg = pop_loadbv(sub_folder, subj_vhdr_file);
    
    srate = eeg.srate;
    dc_end = [];
    dc_start = [];
    
    baseline_start = [];
    baseline_end   = [];
    withdraw_start = [];
    withdraw_end   = [];
    baseline_all_duration = eeg_detail(1);
    baseline_offset = eeg_detail(2);
    dc_all_duration = eeg_detail(3);
    dc_offset = eeg_detail(4);
    withdraw_all_duration = eeg_detail(5);
    withdraw_offset = eeg_detail(6);
    
    baseline_start(end + 1) = (0 + baseline_offset) * srate;
    baseline_end(end + 1) = (baseline_all_duration - baseline_offset) * srate;
    dc_start(end + 1) = baseline_end(end) + (2  + baseline_offset + dc_offset) * srate;
    dc_end(end + 1) = dc_start(end) + (dc_all_duration - dc_offset - dc_offset) * srate;
    withdraw_start(end + 1) = dc_end(end) + (dc_offset + 2 + withdraw_offset)*srate;
    withdraw_end(end + 1) = withdraw_start(end) + (withdraw_all_duration - withdraw_offset - withdraw_offset) * srate;
    
    i = 1;
    data = [];
    data = eeg.data(1:size(eeg.data,1), baseline_start(1, i):baseline_end(1, i)-1);
    path_baseline = [process_dir filesep strcat('baseline', '.mat')];
    save(path_baseline, 'data')
    
    data = [];
    data = eeg.data(1:size(eeg.data,1), withdraw_start(1, i):withdraw_end(1, i)-1);
    path_withdraw = [process_dir filesep strcat('withdraw', '.mat')];
    save(path_withdraw, 'data')
    
    data = [];
    data = eeg.data(1:size(eeg.data,1), dc_start(1, i):dc_end(1, i)-1);
    path_dc       = [process_dir filesep strcat('dc', '.mat')];
    save(path_dc, 'data')
    
end