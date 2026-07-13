function single_preprocess(vhdr_path, subj_bad_chs, set_name, data_save_path, mat_name, info_save_path, segment_length, srate)
    
    mkdir(data_save_path)
    mkdir(info_save_path)
    
    [sub_folder, subj_name] = fileparts(vhdr_path);
    subj_vhdr_file = strcat(subj_name, '.vhdr');
    
    % eeg = pop_loadbv(sub_folder, subj_vhdr_file);
    eeg = load(vhdr_path);
    eeg = pop_importdata('data', eeg.data, 'dataformat', 'array', 'srate',srate);
    channlocs = loadbvef('BC-MR-32.bvef');
    channlocs(1:2)                    = []; % Get rid of GND and REF
    channlocs(end)                    = [];
    ch_all                            = channlocs;
    eeg.chanlocs                      = ch_all;
        
    if ~isempty(subj_bad_chs)
        eeg = pop_select(eeg, 'nochannel', subj_bad_chs);
    end
%     [EEG] = load_EEG(sub_folder, subj_vhdr_file, 2400, 2, 33, slice_mk_path, {});
    reject_min_amp = -200;
    reject_max_amp = 200;

    eeg = eeg_regepochs(eeg,'recurrence',segment_length,'limits', [0, segment_length], 'rmbase', nan);
    
    % set chanlos

    
    eeg_chans = [1:eeg.nbchan];
    ext_chans = [];
    o.epoch_interp_options.rejection_options.measure = [1 1 1 1];
    o.epoch_interp_options.rejection_options.z = [3 3 3 3];
    lengths_ep=cell(1,size(eeg.data,3));
    status = '';
    for v=1:size(eeg.data,3)
        list_properties = single_epoch_channel_properties(eeg,v,eeg_chans);
        lengths_ep{v}=eeg_chans(logical(min_z(list_properties,o.epoch_interp_options.rejection_options)));
        status = [status sprintf('%d: ',v) sprintf('%d ',lengths_ep{v}) sprintf('\n')];
    end
    
    eeg = h_epoch_interp_spl(eeg,lengths_ep,ext_chans);
    eeg.saved = 'no';
    eeg.etc.epoch_interp_info = [status];

    eeg = pop_eegthresh(eeg,1,[1:eeg.nbchan],reject_min_amp,reject_max_amp,eeg.xmin, eeg.xmax,1,0);
    eeg = pop_jointprob(eeg,1,[1:eeg.nbchan],3,3,0,0,0,[],0);
    eeg = eeg_rejsuperpose(eeg, 1, 0, 1, 1, 1, 1, 1, 1);

    bad_epochs = eeg.reject.rejglobal + eeg.reject.rejthresh + eeg.reject.rejjp;
    
    eeg = pop_interp(eeg, ch_all, 'spherical');


    info = {};
    if isfield(eeg.chaninfo, 'removedchans')
        info.bad_chs = eeg.chaninfo.removedchans;
    else
        info.bad_chs = [];
    end

    info.bad_epochs = bad_epochs;

    save([info_save_path filesep mat_name], 'info');

    pop_saveset(eeg,'filename',set_name,'filepath',[data_save_path filesep],'savemode','onefile', 'check', 'off', 'version', '7.3');
end