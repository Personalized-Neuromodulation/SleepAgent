#!/usr/bin/env python3
from __future__ import annotations

import gc
import multiprocessing as mp
import sys
from os import EX_SOFTWARE


def main() -> int:
    try:
        mp.set_start_method("fork")
    except RuntimeError:
        pass

    from fmriprep import config
    from fmriprep.cli.parser import parse_args
    from fmriprep.cli.workflow import build_boilerplate, build_workflow
    from fmriprep.reports.core import generate_reports
    from fmriprep.utils.bids import write_bidsignore, write_derivative_description

    parse_args()
    config.nipype.plugin = "Linear"
    config.nipype.plugin_args = {}

    config_file = config.execution.work_dir / config.execution.run_uuid / "config.toml"
    config_file.parent.mkdir(exist_ok=True, parents=True)
    config.to_filename(config_file)

    retval: dict = {}
    retval = build_workflow(str(config_file), retval) or retval
    exitcode = retval.get("return_code", 0)
    fmriprep_wf = retval.get("workflow", None)

    config.load(config_file)
    config.nipype.plugin = "Linear"
    config.nipype.plugin_args = {}

    if config.execution.reports_only:
        return int(exitcode > 0)

    if fmriprep_wf and config.execution.write_graph:
        fmriprep_wf.write_graph(graph2use="colored", format="svg", simple_form=True)

    exitcode = exitcode or (fmriprep_wf is None) * EX_SOFTWARE
    if exitcode != 0:
        return int(exitcode)

    build_boilerplate(str(config_file), fmriprep_wf)
    if config.execution.boilerplate_only:
        return int(exitcode > 0)

    gc.collect()
    errno = 1
    try:
        fmriprep_wf.run(plugin="Linear", plugin_args={})
    except Exception as exc:
        config.loggers.workflow.critical(f"fMRIPrep failed: {exc}")
        raise
    else:
        config.loggers.workflow.log(25, "fMRIPrep finished successfully!")
        errno = 0
    finally:
        session_list = (
            config.execution.get().get("bids_filters", {}).get("bold", {}).get("session")
        )
        failed_reports = generate_reports(
            config.execution.participant_label,
            config.execution.fmriprep_dir,
            config.execution.run_uuid,
            session_list=session_list,
        )
        write_derivative_description(
            config.execution.bids_dir,
            config.execution.fmriprep_dir,
            dataset_links=config.execution.dataset_links,
        )
        write_bidsignore(config.execution.fmriprep_dir)

    return int((errno + len(failed_reports)) > 0)


if __name__ == "__main__":
    raise SystemExit(main())
