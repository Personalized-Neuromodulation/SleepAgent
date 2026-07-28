from __future__ import annotations

import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path


def build_report(csv_stats,journals,results,profiles,database_snapshot,paths=None,planned_journals=None):
    status=Counter(x["status"] for x in results);adapter=defaultdict(lambda:{"journals_assigned":0,"journals_verified":0,"crawl_success":0,"crawl_failure":0,"papers_discovered":0})
    for p in profiles:
        a=p.get("adapter",{}).get("name","unresolved");adapter[a]["journals_assigned"]+=1;adapter[a]["journals_verified"]+=p.get("verification_status")=="verified"
    success_states={"completed_with_relevant_papers","completed_no_relevant_papers","completed_no_new_papers"}
    for x in results:
        a=x.get("adapter","unresolved");adapter[a]["crawl_success"]+=x["status"] in success_states;adapter[a]["crawl_failure"]+=x["status"] not in success_states;adapter[a]["papers_discovered"]+=x.get("articles_discovered",0)
    attempted=len(results);planned=len(planned_journals if planned_journals is not None else journals);summary={"csv_original_rows":csv_stats["row_count"],"valid_deduplicated_journals":len(journals),"journals_planned":planned,"journals_attempted":attempted,"journals_completed":sum(status[x] for x in success_states),"journals_pending":planned-attempted,"journals_failed":sum(v for k,v in status.items() if k in {"temporarily_failed","permanently_failed","profile_broken"}),"journals_blocked":status["blocked_by_robots"]+status["blocked_by_anti_bot"]+status["login_required"],"journals_manual_review":status["manual_review"]+status["official_url_not_resolved"]+status["listing_url_not_resolved"],"profiles_created":len(profiles),"profiles_verified":sum(p.get("verification_status")=="verified" for p in profiles),"profiles_partial":sum(p.get("verification_status")=="partial" for p in profiles),"profiles_unresolved":sum(p.get("verification_status")=="manual_review" for p in profiles),"coverage_equation_valid":attempted+(planned-attempted)==planned}
    payload={"timestamp":datetime.now(timezone.utc).isoformat(),"overall_result":"PASS" if attempted==planned and not summary["journals_failed"] and summary["coverage_equation_valid"] else "PARTIAL_PASS" if attempted==planned and summary["coverage_equation_valid"] else "FAIL","summary":summary,"web_search_audit":{"html_pages_parsed":sum(x.get("html_page_status")=="parsed" for x in results),"search_forms_found":sum(x.get("search_form_status") in {"found","searched_no_results","searched_with_results"} for x in results),"searches_submitted":sum(bool(x.get("search_queries_attempted")) for x in results),"searches_with_article_results":sum(x.get("search_form_status")=="searched_with_results" for x in results),"search_pages_requested":sum(x.get("search_pages_requested",0) for x in results),"search_pages_succeeded":sum(x.get("search_pages_succeeded",0) for x in results)},"url_resolution":{"homepage_resolved":sum(bool(p.get("homepage_url")) for p in profiles),"listing_url_resolved":sum(any(p.get(x) for x in ("latest_articles_url","current_issue_url","rss_url","sitemap_url")) for p in profiles),"officially_verified":summary["profiles_verified"],"manual_review":summary["profiles_unresolved"],"unresolved":summary["profiles_unresolved"]},"adapter_coverage":dict(adapter),"crawl_results":{key:sum(x.get(key,0) for x in results) for key in ("search_pages_requested","search_pages_succeeded","listing_pages_requested","article_pages_requested","articles_discovered","articles_parsed","non_paper_records_rejected","articles_relevant","articles_uncertain","articles_excluded","candidates_created","papers_created","papers_matched","sample_article_saved")},"status_breakdown":dict(status),"sample_channels":dict(Counter(x.get("sample_discovery_channel") for x in results if x.get("sample_discovery_channel"))),"per_journal_results":results,"failures":[x for x in results if x.get("error")],"database_snapshot":database_snapshot}
    return payload


def write_report(payload,report_dir):
    stamp=payload["timestamp"].replace("-","").replace(":","").split(".")[0]+"Z";root=Path(report_dir);root.mkdir(parents=True,exist_ok=True);jp=root/f"{stamp}_all_journals.json";mp=root/f"{stamp}_all_journals.md";paths={"markdown":str(mp),"json":str(jp)};payload["report_paths"]=paths;jp.write_text(json.dumps(payload,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    rows="\n".join(f"| {x['journal']} | {x.get('issn','')} | {x.get('publisher','')} | {x.get('adapter','')} | {x.get('official_url','')} | {x.get('robots','')} | {x.get('articles_discovered',0)} | {x.get('articles_relevant',0)} | {x.get('candidates_created',0)} | {x.get('papers_created',0)} | {x.get('papers_matched',0)} | {x['status']} | {(x.get('error') or {}).get('message','')} |" for x in payload["per_journal_results"])
    remediation=""
    if payload.get("failure_analysis"):
        remediation=f"\n## Failure analysis and remediation\n\n```json\n{json.dumps(payload['failure_analysis'],indent=2,ensure_ascii=False)}\n```\n"
    coverage=""
    if payload.get("sample_coverage"):
        coverage=f"\n## One-article sample coverage\n\n```json\n{json.dumps(payload['sample_coverage'],indent=2,ensure_ascii=False)}\n```\n"
    validation=""
    if payload.get("database_validation"):
        validation=f"\n## Database validation\n\n```json\n{json.dumps(payload['database_validation'],indent=2,ensure_ascii=False)}\n```\n"
    md=f"# All Target Journals Crawl\n\nOverall result: **{payload['overall_result']}**\n\n## Summary\n\n```json\n{json.dumps(payload['summary'],indent=2)}\n```\n{coverage}{remediation}{validation}\n## Per-journal results\n\n| Journal | ISSN/eISSN | Publisher | Adapter | Official URL | Robots | Discovered | Relevant | Candidates | New Papers | Matched | Status | Error |\n|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|\n{rows}\n\n## URL Resolution\n\n```json\n{json.dumps(payload['url_resolution'],indent=2)}\n```\n\n## Adapter Coverage\n\n```json\n{json.dumps(payload['adapter_coverage'],indent=2)}\n```\n\n## Crawl Results\n\n```json\n{json.dumps(payload['crawl_results'],indent=2)}\n```\n\n## Status Breakdown\n\n```json\n{json.dumps(payload['status_breakdown'],indent=2)}\n```\n\n## Failures\n\n```json\n{json.dumps(payload['failures'],indent=2,ensure_ascii=False)}\n```\n\n## Database Snapshot\n\n```json\n{json.dumps(payload['database_snapshot'],indent=2)}\n```\n";mp.write_text(md,encoding="utf-8");return {"markdown":str(mp),"json":str(jp)}
