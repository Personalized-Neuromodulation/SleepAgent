from __future__ import annotations
from datetime import date,timedelta
from sqlalchemy import select
from .export import export_registry
from .metadata_pipeline import run_metadata_update
from .models import UpdateRun
from .reporting import build_report,write_report
from .repository import LiteratureRepository

def run_weekly_update(session,config,*,dry_run=False,skip_pdf=False,since=None,until=None,api_only=False,journal_only=False,initial_backfill=False,max_journals=None):
    end=date.fromisoformat(until) if until else date.today();days=config["discovery"]["journals"].get("lookback_years",10)*365 if initial_backfill else config["discovery"]["journals"].get("overlap_days",30);start=date.fromisoformat(since) if since else end-timedelta(days=days)
    if dry_run:return run_metadata_update(session,config,dry_run=True,api_only=api_only,journal_only=journal_only,max_journals=max_journals)
    active=session.scalar(select(UpdateRun).where(UpdateRun.run_type=="weekly_update",UpdateRun.status=="running"))
    if active:raise RuntimeError(f"weekly update already running: {active.run_id}")
    repo=LiteratureRepository();run=repo.create_run(session,"weekly_update",discovery_window_start=start,discovery_window_end=end,reporting_window_start=start,reporting_window_end=end,config_snapshot={k:v for k,v in config.items() if not k.startswith('_')})
    summary=run_metadata_update(session,config,api_only=api_only,journal_only=journal_only,max_journals=max_journals);repo.finish_run(session,run)
    root=config["_project_root"];exports=export_registry(session,f"{root}/data/literature/literature_registry.csv",f"{root}/data/literature/literature_registry.jsonl");report=build_report(session,run);paths=write_report(report,config["reporting"]["output_dir"])
    return {"run_id":run.run_id,"status":run.status,"metadata":summary,"skip_pdf":skip_pdf,"exports":exports,"report":paths}
