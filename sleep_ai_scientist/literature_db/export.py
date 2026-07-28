from __future__ import annotations
import csv,json
from pathlib import Path
from sqlalchemy import select
from .models import AbstractVersion,Paper,PaperIdentifier,PaperSource


FIELDS=list(__import__('sleep_ai_scientist.schemas.literature',fromlist=['LiteratureRecord']).LiteratureRecord.model_fields)


def export_registry(session,csv_path,jsonl_path):
    rows=[]
    for p in session.scalars(select(Paper).order_by(Paper.created_at)):
        ids={x.identifier_type:x.normalized_value for x in session.scalars(select(PaperIdentifier).where(PaperIdentifier.paper_id==p.paper_id))}
        abstract=session.get(AbstractVersion,p.preferred_abstract_id) if p.preferred_abstract_id else None
        sources=list(session.scalars(select(PaperSource).where(PaperSource.paper_id==p.paper_id)))
        row={k:"" for k in FIELDS};row.update({"paper_id":p.paper_id,"title":p.canonical_title,"abstract":abstract.abstract_text if abstract else "","year":p.publication_year,"publication_year":p.publication_year,"doi":ids.get("doi","") ,"pmid":ids.get("pmid","") ,"pmcid":ids.get("pmcid"),"journal":p.journal,"publication_type":p.article_type,"source":";".join(sorted({s.source_name for s in sources})),"provider":sources[0].source_name if sources else None,"authors":[] ,"keywords":[]})
        rows.append(row)
    for path in (Path(csv_path),Path(jsonl_path)):path.parent.mkdir(parents=True,exist_ok=True)
    with Path(csv_path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    with Path(jsonl_path).open("w",encoding="utf-8") as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False,default=str)+"\n")
    return {"count":len(rows),"csv":str(csv_path),"jsonl":str(jsonl_path)}
