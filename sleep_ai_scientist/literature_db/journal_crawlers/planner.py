from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class JournalPlanItem:
    journal: object
    since: date
    until: date
    retry: bool=False


def build_scan_plan(journals,states,config,*,limit_journals=None,since=None,until=None,resume=False,retry_failed=False):
    end=until or date.today();lookback=config["publication_window"].get("lookback_days",365);overlap=config["publication_window"].get("overlap_days",30)
    result=[]
    for journal in journals:
        state=states.get(journal.journal_key);start=since or end-timedelta(days=lookback)
        if resume and state and state.last_successful_scan_at:start=state.last_successful_scan_at.date()-timedelta(days=overlap)
        if resume and state and state.status in {"completed_no_relevant_papers","completed_no_new_papers","completed_with_relevant_papers"} and state.last_attempted_at and state.last_attempted_at.date()>=end:continue
        failed=bool(state and state.status in {"temporarily_failed","partial"})
        retryable=bool(failed and (getattr(state,"last_error",None) or {}).get("retryable",True))
        if resume and state and state.status in {
            "blocked_by_robots", "blocked_by_anti_bot", "login_required",
            "official_url_not_resolved", "listing_url_not_resolved",
            "profile_broken", "permanently_failed", "manual_review",
        }:
            continue
        if failed and (not retry_failed or not retryable):continue
        result.append(JournalPlanItem(journal,start,end,failed))
    return result[:limit_journals] if limit_journals is not None else result
