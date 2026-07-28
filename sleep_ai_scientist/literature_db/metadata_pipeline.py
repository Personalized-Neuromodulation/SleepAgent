from __future__ import annotations
import json
from pathlib import Path
from .repository import LiteratureRepository
from .schemas import CandidateInput


def import_metadata(session,path: str|Path,run_id=None):
    repo=LiteratureRepository(); result={"processed":0,"created":0,"matched":0,"manual_review":0}
    with Path(path).open(encoding="utf-8") as fh:
        for line_no,line in enumerate(fh,1):
            if not line.strip():continue
            row=json.loads(line)
            if "paper_id" in row: raise ValueError(f"line {line_no}: paper_id is system-generated and must not be supplied")
            row["source_name"]=row.get("source_name","manual_metadata");row["source_record_id"]=row.get("source_record_id",f"{Path(path).name}:{line_no}");row["discovery_method"]="manual_metadata_import"
            _,_,decision=repo.ingest(session,CandidateInput(**row),run_id);result["processed"]+=1
            if decision.decision=="create_new":result["created"]+=1
            elif decision.requires_manual_review:result["manual_review"]+=1
            else:result["matched"]+=1
    return result


def run_metadata_update(session,config,*,dry_run=False,api_only=False,journal_only=False,**kwargs):
    # Discovery providers are injected by callers/tests. Dry-run deliberately makes no DB writes or network calls.
    journals=[]
    if not api_only:
        from .target_journals import TargetJournalLoader
        loader=TargetJournalLoader(config["discovery"]["journals"]["journal_file"]);journals=loader.load()
        max_journals=kwargs.get("max_journals") or config["discovery"]["journals"].get("max_journals")
        if max_journals:journals=journals[:int(max_journals)]
    return {"dry_run":dry_run,"channels":[x for x,on in (("api",not journal_only),("journals",not api_only)) if on],"target_journals":len(journals),"candidates":0,"created_papers":0}
