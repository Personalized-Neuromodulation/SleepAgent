# Scientific Loop Report

## Inputs
- top_k_hypotheses: /home/jwj/code/SleepAgent/outputs/hypotheses/top_k_hypotheses.json
- master_table: /home/jwj/code/SleepAgent/data/foundation/multimodal_master_table.csv

## Top Hypotheses
- H006: Thalamus-DMN connectivity association with insomnia severity (score=0.8395)
- H003: Slow-wave density association with insomnia severity (score=0.835)
- H002: INS vs HC beta power difference (score=0.8148)
- H004: Spindle density association with thalamocortical coupling (score=0.8145)
- H001: INS vs HC slow-wave density difference (score=0.804)

## Experiments
- EXP_H001: n_used=4, corrected_p={'group': 0.0455, 'medication': 0.0455}
- EXP_H002: n_used=4, corrected_p={'group': 0.515798, 'medication': 0.729034}
- EXP_H003: n_used=4, corrected_p={'slow_wave_density': 0.385696, 'medication': 0.445598}
- EXP_H004: n_used=5, corrected_p={'spindle_density': 0.0, 'mean_FD': 0.0, 'in_scanner_sleep_time': 0.0, 'medication': 0.0}
- EXP_H005: n_used=4, corrected_p={'thalamic_radiation_FA': 0.0, 'medication': 0.715001}
- EXP_H006: n_used=5, corrected_p={'thalamus_DMN_FC': 0.0, 'mean_FD': 0.0, 'in_scanner_sleep_time': 0.0, 'medication': 0.0}

## Critic Decisions
- EXP_H001: revised / exploratory_association
- EXP_H002: hold / not_supported
- EXP_H003: hold / not_supported
- EXP_H004: revised / exploratory_association
- EXP_H005: revised / exploratory_association
- EXP_H006: revised / exploratory_association

## Co-Scientist Inputs
- outputs/hypotheses/hypothesis_registry.csv
- outputs/hypotheses/hypothesis_lineage.json
- outputs/experiments/results/
- outputs/experiments/critic_reviews/
- outputs/memory/null_findings_registry.csv
