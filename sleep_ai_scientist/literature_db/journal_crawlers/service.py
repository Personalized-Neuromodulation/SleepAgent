from __future__ import annotations

import json
import os
import re
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import func,select,text,update
from sqlalchemy.orm import Session,sessionmaker

from sleep_ai_scientist.common.config import resolve_path
from ..config import load_literature_db_config
from ..engine import create_database_engine
from ..models import CandidateRecord,JournalCrawlRun,JournalScanState,JournalScraperProfile,JournalURL,Paper
from ..normalization import normalize_date, normalize_journal, normalize_title
from ..repository import LiteratureRepository
from ..schemas import AbstractVersionCreate,CandidateCreate,DedupDecisionCreate,IdentifierCreate,JournalScanStateCreate,JournalScraperProfileCreate,JournalURLCreate,PaperAuthorCreate,PaperCreate,PaperSourceCreate,UpdateRunCreate
from ..target_journals import TargetJournalLoader
from .http_client import CrawlHTTPClient
from .metadata_parser import discover_html_links,discover_search_forms,parse_article_html,parse_feed,parse_feed_metadata,parse_jats_xml,parse_sitemap,render_search_url
from .paper_validation import assess_paper_metadata
from .planner import build_scan_plan
from .profiles import make_profile,write_profiles
from .publisher_api import fetch_sciencedirect_search,is_sciencedirect_journal
from .publisher_native import publisher_native_entries
from .registry import JournalCrawlerRegistry
from .relevance import classify_relevance
from .reporting import build_report,write_report
from .robots import RobotsCache
from .url_resolver import JournalURLResolver,normalize_url


FINAL_STATUSES={"completed_with_relevant_papers","completed_no_relevant_papers","completed_no_new_papers","partial","blocked_by_robots","blocked_by_anti_bot","login_required","official_url_not_resolved","listing_url_not_resolved","profile_broken","temporarily_failed","permanently_failed","manual_review"}


class JournalCrawlService:
    def __init__(self,config_path,http_client=None):
        self.config_path=config_path;self.config=load_literature_db_config(config_path);self.root=Path(self.config["_project_root"]);self.crawl=self.config["journal_crawl"]
        self.engine=create_database_engine(config_path);self.sessions=sessionmaker(self.engine,expire_on_commit=False,future=True)
        loader=TargetJournalLoader(resolve_path(self.crawl["target_journal_file"],self.root));self.journals=loader.load();self.csv_stats=loader.stats
        cache=resolve_path(self.crawl["cache_dir"],self.root);self.http=http_client or CrawlHTTPClient(cache,self.crawl["request_policy"])
        self._robots=RobotsCache(self.http)
        self.resolver=JournalURLResolver(self.http,cache,os.getenv("NCBI_EMAIL",""));self.profile_dir=resolve_path(self.crawl["profile_dir"],self.root)
    def close(self):self.engine.dispose()
    def _ensure_state(self,session,journal,status=None):
        existing=session.get(JournalScanState,journal.journal_key)
        if existing:
            existing.title=journal.title;existing.normalized_title=journal.normalized_title;existing.issn=journal.issn;existing.eissn=journal.eissn;existing.source_row_numbers=journal.source_row_numbers
            if journal.publisher:existing.publisher=journal.publisher
            if status:existing.status=status
            return existing
        return LiteratureRepository().upsert_journal_scan_state(session,JournalScanStateCreate(journal_key=journal.journal_key,title=journal.title,normalized_title=journal.normalized_title,issn=journal.issn,eissn=journal.eissn,publisher=journal.publisher,identifier_quality=journal.identifier_quality,source_file=self.crawl["target_journal_file"],source_row_numbers=journal.source_row_numbers,status=status or "pending",last_error={"warnings":journal.warnings} if journal.warnings else None))
    def resolve_all(self,limit_journals=None):
        journals=self.journals[:limit_journals] if limit_journals is not None else self.journals;results=[]
        for journal in journals:
            with self.sessions.begin() as session:
                state=self._ensure_state(session,journal,"resolving_url");urls,publisher,error=self.resolver.resolve(journal)
                session.execute(update(JournalURL).where(JournalURL.journal_key==journal.journal_key).values(is_active=False))
                if publisher:state.publisher=publisher;journal.publisher=publisher
                for item in urls:
                    LiteratureRepository().upsert_journal_url(session,journal.journal_key,JournalURLCreate(url=item.url,normalized_url=normalize_url(item.url),url_type=item.url_type,resolution_source=item.resolution_source,resolution_method=item.resolution_method,confidence=item.confidence,is_official=item.is_official,is_active=True,requires_manual_review=item.requires_manual_review,last_http_status=item.http_status,last_verified_at=datetime.now(timezone.utc),last_error=item.error))
                official=next((x for x in urls if x.url_type=="homepage" and x.is_official and not x.requires_manual_review),None);candidate=next((x for x in urls if x.url_type=="homepage"),None)
                state.status="profile_pending" if official else "manual_review" if candidate else "official_url_not_resolved";state.last_error=error;state.last_attempted_at=datetime.now(timezone.utc)
                results.append({"journal_key":journal.journal_key,"title":journal.title,"issn":journal.issn,"eissn":journal.eissn,"urls":len(urls),"homepage_url":candidate.url if candidate else None,"is_official":bool(official),"requires_manual_review":bool(candidate and not official),"resolution_source":candidate.resolution_source if candidate else None,"confidence":candidate.confidence if candidate else None,"publisher":publisher,"status":state.status,"error":error})
        # A URL shared by distinct target journals is a publisher/platform landing page,
        # not a verified journal homepage.  Downgrade every collision conservatively.
        collisions=defaultdict(list)
        with self.sessions.begin() as session:
            homepages=list(session.scalars(select(JournalURL).where(JournalURL.url_type=="homepage",JournalURL.is_active.is_(True),JournalURL.is_official.is_(True))))
            for row in homepages:collisions[row.normalized_url].append(row)
            result_by_key={x["journal_key"]:x for x in results}
            for normalized,rows in collisions.items():
                keys={x.journal_key for x in rows}
                if len(keys)<2:continue
                error={"code":"SHARED_PUBLISHER_URL","message":f"Homepage is shared by {len(keys)} target journals","normalized_url":normalized,"retryable":False}
                for row in rows:
                    row.is_official=False;row.requires_manual_review=True;row.last_error=error
                    state=session.get(JournalScanState,row.journal_key);state.status="manual_review";state.last_error=error
                    if row.journal_key in result_by_key:result_by_key[row.journal_key].update(is_official=False,requires_manual_review=True,status="manual_review",error=error)
        verified=sum(x["is_official"] for x in results);manual=sum(x["requires_manual_review"] for x in results);unresolved=sum(not x["homepage_url"] for x in results)
        payload={"timestamp":datetime.now(timezone.utc).isoformat(),"csv":self.csv_stats,"journals_total":len(self.journals),"journals_processed":len(results),"officially_verified":verified,"manual_review":manual,"unresolved":unresolved,"shared_url_collisions":sum(1 for rows in collisions.values() if len({x.journal_key for x in rows})>1),"results":results}
        report_dir=resolve_path(self.crawl["report_dir"],self.root);report_dir.mkdir(parents=True,exist_ok=True);stamp=payload["timestamp"].replace("-","").replace(":","").split(".")[0]+"Z";jp=report_dir/f"{stamp}_url_validation.json";mp=report_dir/f"{stamp}_url_validation.md";payload["report_paths"]={"markdown":str(mp),"json":str(jp)}
        jp.write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        rows="\n".join(f"| {x['title']} | {x.get('issn') or ''}/{x.get('eissn') or ''} | {x.get('homepage_url') or ''} | {x.get('resolution_source') or ''} | {x.get('confidence') or ''} | {x['status']} | {(x.get('error') or {}).get('code','')} |" for x in results)
        mp.write_text(f"# Target Journal URL Validation\n\nVerified: **{verified}**  \nManual review: **{manual}**  \nUnresolved: **{unresolved}**\n\n| Journal | ISSN/eISSN | Homepage | Source | Confidence | Status | Error |\n|---|---|---|---|---:|---|---|\n{rows}\n",encoding="utf-8")
        return payload
    def build_profiles(self,limit_journals=None):
        journals=self.journals[:limit_journals] if limit_journals is not None else self.journals;profiles=[]
        with self.sessions() as session:
            for journal in journals:
                state=self._ensure_state(session,journal);journal.publisher=state.publisher
                urls=list(session.scalars(select(JournalURL).where(JournalURL.journal_key==journal.journal_key)))
                profile=make_profile(journal,urls,self.crawl["request_policy"]);profiles.append(profile)
                data=profile.to_dict();data.pop("journal_key");data.pop("title");data.pop("publisher")
                LiteratureRepository().upsert_scraper_profile(session,journal.journal_key,JournalScraperProfileCreate(**data));state.status="profile_ready" if profile.enabled else "manual_review";state.last_error=profile.last_error
                session.commit()
        index=write_profiles(self.profile_dir,profiles)
        return {"journals_total":len(self.journals),"profiles_created":len(index),"verified":sum(x.verification_status=="verified" for x in profiles),"partial":sum(x.verification_status=="partial" for x in profiles),"manual_review":sum(x.verification_status=="manual_review" for x in profiles),"index":str(self.profile_dir/"index.yaml")}
    def _ingest(self,session,repo,run,journal,metadata,relevance,force_canonical=False):
        if metadata.discovery_channel=="publisher_api":
            source_prefix=f"journal_publisher_api:{metadata.discovery_provider or 'unknown'}";method="target_journal_publisher_api_search"
        elif metadata.discovery_channel=="api_fallback":
            source_prefix=f"journal_api:{metadata.discovery_provider or 'unknown'}";method="target_journal_api_fallback"
        else:
            source_prefix="journal_web";method="target_journal_web_crawl"
        source=f"{source_prefix}:{journal.journal_key}"
        before_candidates=session.scalar(select(func.count()).select_from(CandidateRecord));candidate=repo.create_candidate(session,CandidateCreate(source_name=source,source_record_id=metadata.doi or metadata.source_url,discovery_method=method,target_journal_key=journal.journal_key,raw_title=metadata.title,raw_abstract=metadata.abstract,raw_doi=metadata.doi,raw_pmid=metadata.pmid,raw_pmcid=metadata.pmcid,raw_journal=metadata.journal or journal.title,raw_authors=metadata.authors,raw_publication_date=metadata.publication_date,raw_payload={**metadata.to_dict(),"relevance_score":relevance.score,"matched_terms":relevance.matched_terms},relevance_status=relevance.status),run=run);candidate_created=int(session.scalar(select(func.count()).select_from(CandidateRecord))>before_candidates)
        if relevance.status=="uncertain" and not force_canonical:repo.record_dedup_decision(session,candidate,DedupDecisionCreate(decision="manual_review",match_method="deterministic_relevance",match_score=relevance.score,requires_manual_review=True));return candidate_created,0,0
        paper=None;match_method="none"
        for kind,value in (("doi",metadata.doi),("pmid",metadata.pmid),("pmcid",metadata.pmcid)):
            if value:
                paper=repo.find_paper_by_identifier(session,kind,value)
                if paper:match_method=kind;break
        if paper is None:
            parsed_date=normalize_date(metadata.publication_date);year=parsed_date.year if parsed_date else None
            candidates=session.scalars(select(Paper).where(Paper.normalized_title==normalize_title(metadata.title),Paper.publication_year==year)).all() if year else []
            first=" ".join(filter(None,[(metadata.authors[0].get("given_name") if metadata.authors else None),(metadata.authors[0].get("family_name") if metadata.authors else None)]))
            paper=next((p for p in candidates if (first and p.first_author and p.first_author.casefold()==first.casefold()) or normalize_journal(p.journal_name)==normalize_journal(metadata.journal or journal.title)),None)
            if paper:match_method="title_year_author_journal"
        if paper is None:
            paper=repo.create_canonical_paper(session,PaperCreate(canonical_title=metadata.title,journal_name=metadata.journal or journal.title,publication_date=metadata.publication_date,volume=metadata.volume,issue=metadata.issue,pages=metadata.pages,article_type=metadata.article_type,language=metadata.language,first_author=" ".join(filter(None,[(metadata.authors[0].get("given_name") if metadata.authors else None),(metadata.authors[0].get("family_name") if metadata.authors else None)])) or None,keywords=metadata.keywords));decision="create_new"
            if metadata.authors:
                authors=[]
                for i,a in enumerate(metadata.authors):
                    raw=a.get("raw",a);raw=raw if isinstance(raw,dict) else {"name":str(raw)}
                    authors.append(PaperAuthorCreate(author_order=i+1,given_name=a.get("given_name"),family_name=a.get("family_name"),orcid=a.get("orcid"),source_name=source,raw_author=raw))
                repo.replace_paper_authors(session,paper,authors)
        else:decision="exact_match"
        for kind,value in (("doi",metadata.doi),("pmid",metadata.pmid),("pmcid",metadata.pmcid)):
            if value:repo.add_identifier(session,paper,IdentifierCreate(identifier_type=kind,raw_value=value,source_name=source,is_primary=kind=="doi"))
        repo.add_paper_source(session,paper,candidate,PaperSourceCreate(source_name=source,source_record_id=metadata.doi or metadata.source_url,discovery_method=method,match_method=match_method if decision=="exact_match" else "create_new",match_score=1.0 if match_method else None))
        if metadata.abstract:
            abstract=repo.add_abstract_version(session,paper,AbstractVersionCreate(source_name=source,abstract_text=metadata.abstract,quality_score=min(1,len(metadata.abstract)/2000)))
            preferred=session.scalar(select(func.count()).select_from(type(abstract)).where(type(abstract).paper_id==paper.paper_id,type(abstract).is_preferred.is_(True)))
            if not preferred:repo.set_preferred_abstract(session,paper,abstract)
        repo.record_dedup_decision(session,candidate,DedupDecisionCreate(decision=decision,match_method=match_method if decision=="exact_match" else "no_match",match_score=1.0 if decision=="exact_match" else None),matched_paper=paper)
        return candidate_created,int(decision=="create_new"),int(decision=="exact_match")

    def _scan_one(self,journal,profile,run_id,limits,since=None,until=None):
        result={"journal_key":journal.journal_key,"journal":journal.title,"issn":"/".join(filter(None,[journal.issn,journal.eissn])),"publisher":journal.publisher,"adapter":profile.adapter_name,"official_url":profile.homepage_url,"primary_method":"web_search","fallback_method":"publisher_native","publisher_native_urls":[],"official_api_status":"not_applicable","official_api_provider":None,"official_api_query":None,"articles_parsed_from_official_api":0,"html_page_status":"not_attempted","search_form_status":"not_checked","search_form":None,"search_queries_attempted":[],"search_result_urls":[],"search_pages_requested":0,"search_pages_succeeded":0,"articles_parsed_from_search":0,"robots":None,"listing_pages_requested":0,"listing_pages_succeeded":0,"article_pages_requested":0,"article_pages_succeeded":0,"http_status_counts":{},"articles_discovered":0,"articles_parsed":0,"non_paper_records_rejected":0,"non_paper_rejection_examples":[],"articles_relevant":0,"articles_uncertain":0,"articles_excluded":0,"candidates_created":0,"papers_created":0,"papers_matched":0,"sample_article_saved":0,"sample_discovery_channel":None,"sample_discovery_provider":None,"last_cursor":None,"last_seen_publication_date":None,"status":"temporarily_failed","error":None}
        discovered_metadata_count=0
        def validated_papers(candidates):
            accepted=[]
            for item in candidates:
                assessment=assess_paper_metadata(item,journal)
                item.raw_metadata["_paper_validation"]=assessment.to_dict()
                if assessment.is_paper:
                    accepted.append(item)
                else:
                    result["non_paper_records_rejected"]+=1
                    if len(result["non_paper_rejection_examples"])<5:
                        result["non_paper_rejection_examples"].append({
                            "title":item.title,"source_url":item.source_url,
                            "reasons":assessment.reasons,
                        })
            return accepted
        with self.sessions.begin() as session:
            crawl_run=JournalCrawlRun(update_run_id=run_id,journal_key=journal.journal_key,scraper_profile_id=profile.scraper_profile_id,status="running");session.add(crawl_run);session.flush();crawl_id=crawl_run.crawl_run_id
        if not profile.enabled or not profile.homepage_url:
            base=profile.last_error or {};result["status"]="official_url_not_resolved";result["error"]={"journal_key":journal.journal_key,"journal_title":journal.title,"publisher":journal.publisher,"adapter":profile.adapter_name,"stage":"profile","url":None,"code":base.get("code","JOURNAL_URL_NOT_FOUND"),"message":base.get("message","Profile unresolved"),"retryable":False,"recommended_action":"Resolve or verify an official URL manually"};return self._finish_one(journal,crawl_id,result)
        metadata=[];search_article_urls=[]
        try:
            robots=self._robots
            robot_status,allowed=robots.check(profile.homepage_url);result["robots"]=robot_status
            if allowed:
                result["listing_pages_requested"]+=1
                try:status,body,final,_=self.http.get(profile.homepage_url)
                except Exception as exc:
                    status,body,final=0,b"",profile.homepage_url;result["status"]="partial";result["error"]={"stage":"homepage","code":"HTTP_REQUEST_FAILED","message":str(exc),"retryable":True,"recommended_action":"Retry website later; metadata fallback was attempted"}
                result["http_status_counts"][str(status)]=result["http_status_counts"].get(str(status),0)+1
                result["html_page_status"]="parsed" if 0<status<400 else f"http_{status}" if status else "request_failed"
                if 0<status<400:result["listing_pages_succeeded"]+=1
                homepage_html=body.decode("utf-8",errors="ignore");low=homepage_html[:20000].casefold()
                if status==0:pass
                elif status==401:result["status"]="login_required";result["error"]={"stage":"homepage","code":"LOGIN_REQUIRED","message":"Homepage requires login","retryable":False,"recommended_action":"Use public metadata fallback only"}
                elif status in {403,429} or any(marker in low for marker in ("<title>just a moment","cf-chl-","challenge-platform","g-recaptcha-response")):result["status"]="blocked_by_anti_bot";result["error"]={"stage":"homepage","code":"ANTI_BOT_BLOCK","message":f"Anti-bot response HTTP {status}","retryable":False,"recommended_action":"Use a robots-allowed publisher feed or listing"}
                elif status>=400:result["status"]="partial";result["error"]={"stage":"homepage","code":"HTTP_ERROR","message":f"Homepage returned HTTP {status}","retryable":status>=500,"recommended_action":"Retry or review URL"}
                else:
                    links=discover_html_links(homepage_html,final);entries=(links["rss"]+links["sitemap"]+links["listing"])[:limits["listing_pages"]]
                    forms=discover_search_forms(homepage_html,final)
                    result["search_form_status"]="found" if forms else "not_found"
                    selected_form=next((form for form in forms if form["supported"]),forms[0] if forms else None)
                    if selected_form:
                        result["search_form"]={key:selected_form.get(key) for key in ("action","method","query_field","url_template","supported")}
                        if selected_form["supported"]:
                            queries=self.crawl.get("search_queries") or ["sleep"]
                            search_blocked=False
                            for query in queries[:limits.get("search_queries",1)]:
                                search_url=render_search_url(selected_form["url_template"],query)
                                _,search_allowed=robots.check(search_url)
                                if not search_allowed:
                                    search_blocked=True;continue
                                result["search_queries_attempted"].append(query);result["search_pages_requested"]+=1
                                try:ss,sb,su,_=self.http.get(search_url)
                                except Exception:continue
                                result["http_status_counts"][str(ss)]=result["http_status_counts"].get(str(ss),0)+1
                                if ss>=400:continue
                                result["search_pages_succeeded"]+=1
                                found=discover_html_links(sb.decode("utf-8",errors="replace"),su)["article"]
                                search_article_urls.extend(found);result["search_result_urls"].extend(found[:limits["article_pages"]])
                            if result["search_queries_attempted"]:
                                result["search_form_status"]="searched_with_results" if search_article_urls else "searched_no_results"
                            elif search_blocked:result["search_form_status"]="blocked_by_robots"
                        else:result["search_form_status"]="unsupported_post"
                    with self.sessions.begin() as session:
                        stored=session.get(JournalScraperProfile,profile.scraper_profile_id);repo=LiteratureRepository();now=datetime.now(timezone.utc)
                        for kind,values in (("rss",links["rss"]),("sitemap",links["sitemap"]),("latest_articles",links["listing"])):
                            for discovered_url in values[:1]:repo.upsert_journal_url(session,journal.journal_key,JournalURLCreate(url=discovered_url,normalized_url=normalize_url(discovered_url),url_type=kind,resolution_source="publisher_homepage",resolution_method="html_link_discovery",confidence=0.7,is_official=True,last_verified_at=now))
                        if links["rss"]:stored.rss_url=links["rss"][0]
                        if links["sitemap"]:stored.sitemap_url=links["sitemap"][0]
                        if links["listing"]:stored.latest_articles_url=links["listing"][0]
                        if selected_form and selected_form["supported"]:
                            stored.search_url_template=selected_form["url_template"]
                            stored.discovery_rules={**(stored.discovery_rules or {}),"search_form":result["search_form"]}
                        if entries:stored.verification_status="verified";stored.last_verified_at=now
                    if not entries and not search_article_urls:result["status"]="partial";result["error"]={"stage":"listing_resolution","code":"LISTING_URL_NOT_RESOLVED","message":"No searchable results, feed, sitemap, latest, current issue, or archive link found","retryable":False,"recommended_action":"Review profile search and listing rules"}
                    # A homepage canonical URL or a promotional article link is not
                    # sufficient provenance. Article candidates must be discovered
                    # from a publication list, feed, sitemap, or issue/archive page.
                    article_urls=list(search_article_urls)
                    for entry in entries:
                        rs,ok=robots.check(entry)
                        if not ok:continue
                        result["listing_pages_requested"]+=1;s,b,u,_=self.http.get(entry)
                        result["http_status_counts"][str(s)]=result["http_status_counts"].get(str(s),0)+1
                        if s>=400:continue
                        result["listing_pages_succeeded"]+=1
                        content=b.decode("utf-8",errors="replace")
                        try:
                            if entry in links["rss"]:
                                metadata.extend(parse_feed_metadata(content));found=parse_feed(content)
                            else:found=parse_sitemap(content) if entry in links["sitemap"] else discover_html_links(content,u)["article"]
                        except Exception:found=[]
                        article_urls.extend(found)
                    for article_url in list(dict.fromkeys(article_urls))[:limits["article_pages"]]:
                        rs,ok=robots.check(article_url)
                        if not ok:continue
                        result["article_pages_requested"]+=1;s,b,u,_=self.http.get(article_url)
                        result["http_status_counts"][str(s)]=result["http_status_counts"].get(str(s),0)+1
                        if s>=400:continue
                        result["article_pages_succeeded"]+=1
                        parsed=parse_article_html(b.decode("utf-8",errors="replace"),u)
                        if parsed:
                            if article_url in search_article_urls:parsed.raw_metadata["_web_search"]={"queries":result["search_queries_attempted"],"result_url":article_url}
                            metadata.append(parsed)
            elif robot_status=="disallowed":result["status"]="blocked_by_robots"
            else:result["status"]="partial";result["error"]={"stage":"robots","code":"ROBOTS_UNAVAILABLE","message":"robots.txt unavailable; web crawling skipped cautiously","retryable":True,"recommended_action":"Retry robots.txt later"}

            # A blocked homepage must not silently turn into an aggregator
            # success.  Try publisher-owned feeds/listings directly and keep
            # their provenance as web crawl metadata.
            native_entries=list(publisher_native_entries(profile.homepage_url,journal))
            for kind,url in (
                ("rss",profile.rss_url),
                ("sitemap",profile.sitemap_url),
                ("listing",profile.latest_articles_url),
                ("listing",profile.current_issue_url),
                ("listing",profile.archive_url),
            ):
                if url and url != profile.homepage_url:
                    native_entries.append((kind,url))
            native_entries=list(dict.fromkeys(native_entries))[:limits["listing_pages"]]
            native_article_urls=[]
            native_metadata=[]
            for kind,entry in native_entries:
                _,ok=robots.check(entry)
                if not ok:
                    continue
                result["listing_pages_requested"]+=1
                try:
                    s,b,u,_=self.http.get(entry)
                except Exception:
                    continue
                result["http_status_counts"][str(s)]=result["http_status_counts"].get(str(s),0)+1
                if s>=400:
                    continue
                result["listing_pages_succeeded"]+=1
                result["publisher_native_urls"].append(u)
                content=b.decode("utf-8",errors="replace")
                try:
                    if kind=="rss":
                        native_metadata.extend(parse_feed_metadata(content))
                        native_article_urls.extend(parse_feed(content))
                    elif kind=="sitemap":
                        native_article_urls.extend(parse_sitemap(content))
                    else:
                        native_article_urls.extend(discover_html_links(content,u)["article"])
                except Exception:
                    continue
            # Feed metadata is already article-level publisher metadata, so only
            # spend article requests when the feed/listing did not supply enough
            # direct records.
            feed_is_bibliographically_complete=any(
                item.doi and item.journal and item.publication_date
                for item in native_metadata
            )
            if not feed_is_bibliographically_complete:
                for article_url in list(dict.fromkeys(native_article_urls))[:limits["article_pages"]]:
                    if "/article/export/" in article_url:
                        continue
                    request_url=article_url
                    parts=urlsplit(article_url)
                    if (parts.netloc=="www.jmir.org" or parts.netloc.endswith(".jmir.org")) and re.search(r"/20\d{2}/\d+/e?\d+/?$",parts.path):
                        request_url=article_url.rstrip("/")+"/xml"
                    _,ok=robots.check(request_url)
                    if not ok:
                        continue
                    result["article_pages_requested"]+=1
                    try:
                        s,b,u,_=self.http.get(request_url)
                    except Exception:
                        continue
                    result["http_status_counts"][str(s)]=result["http_status_counts"].get(str(s),0)+1
                    if s>=400:
                        continue
                    result["article_pages_succeeded"]+=1
                    content=b.decode("utf-8",errors="replace")
                    try:parsed=parse_jats_xml(content,u) if request_url.endswith("/xml") else parse_article_html(content,u)
                    except Exception:parsed=None
                    if parsed:
                        native_metadata.append(parsed)
            if native_metadata:
                metadata.extend(native_metadata)
                if result["status"] in {"blocked_by_robots","blocked_by_anti_bot","login_required","partial"}:
                    result["status"]="temporarily_failed"
                    result["error"]=None
            if is_sciencedirect_journal(profile.homepage_url):
                result["official_api_provider"]="elsevier_sciencedirect"
                query=(self.crawl.get("search_queries") or ["sleep"])[0]
                result["official_api_query"]=query
                direct_rows,direct_error=fetch_sciencedirect_search(
                    self.http,journal,query,os.getenv("ELSEVIER_API_KEY",""),limits["article_pages"]
                )
                result["official_api_status"]="succeeded" if direct_rows else "credentials_missing" if (direct_error or {}).get("code")=="ELSEVIER_API_KEY_MISSING" else "failed"
                if direct_rows:
                    metadata.extend(direct_rows)
                    if result["status"] in {"blocked_by_robots","blocked_by_anti_bot","login_required","partial"}:
                        result["status"]="temporarily_failed";result["error"]=None
            discovered_metadata_count+=len(metadata)
            metadata=validated_papers(metadata)
            result["articles_parsed_from_search"]=sum(bool((item.raw_metadata or {}).get("_web_search")) for item in metadata)
            result["articles_parsed_from_official_api"]=sum(item.discovery_channel=="publisher_api" for item in metadata)
            # Metadata APIs are optional for ordinary no-result scans. They are
            # never used to relabel a robots/403 failure as solved.
            api_allowed=bool(self.crawl["request_policy"].get("use_crossref",False)) and result["status"] not in {"blocked_by_robots","blocked_by_anti_bot","login_required"}
            if api_allowed and (not limits.get("sample_one_article") or not metadata):
                items=[]
                try:
                    items,_=self.resolver.fetch_crossref(journal,rows=limits["article_pages"],lookback_days=self.crawl["publication_window"]["lookback_days"],from_date=since,until=until)
                    if not items:items,_=self.resolver.fetch_crossref(journal,rows=limits["article_pages"],lookback_days=3650)
                except Exception:pass
                if not items:
                    try:items=self.resolver.fetch_crossref_works_by_issn(journal,rows=limits["article_pages"])
                    except Exception:pass
                fallback_metadata=[self.resolver.item_to_metadata(x) for x in items if x.get("title")]
                discovered_metadata_count+=len(fallback_metadata)
                accepted_fallback=validated_papers(fallback_metadata)
                if not accepted_fallback:
                    try:
                        fallback_metadata=[self.resolver.openalex_item_to_metadata(x) for x in self.resolver.fetch_openalex_works(journal,rows=limits["article_pages"]) if x.get("title") or x.get("display_name")]
                    except Exception:fallback_metadata=[]
                    discovered_metadata_count+=len(fallback_metadata)
                    accepted_fallback=validated_papers(fallback_metadata)
                if not accepted_fallback:
                    try:
                        fallback_metadata=[self.resolver.europe_pmc_item_to_metadata(x) for x in self.resolver.fetch_europe_pmc_works(journal,rows=limits["article_pages"]) if x.get("title")]
                    except Exception:fallback_metadata=[]
                    discovered_metadata_count+=len(fallback_metadata)
                    accepted_fallback=validated_papers(fallback_metadata)
                metadata.extend(accepted_fallback)
                if not metadata and result.get("error") is None:
                    result["error"]={"stage":"metadata_fallback","code":"METADATA_NOT_FOUND","message":"No article metadata found via publisher website or configured metadata APIs","retryable":False,"recommended_action":"Review journal identifiers and add a manual publisher endpoint"}
                    if result["status"]=="temporarily_failed":result["status"]="partial"
            if (since or until) and not limits.get("sample_one_article"):
                metadata=[x for x in metadata if not normalize_date(x.publication_date) or (not since or normalize_date(x.publication_date)>=since) and (not until or normalize_date(x.publication_date)<=until)]
            unique={m.doi.casefold() if m.doi else m.source_url:m for m in metadata};metadata=list(unique.values());result["articles_discovered"]=discovered_metadata_count;result["articles_parsed"]=len(metadata)
            if not metadata and result.get("error") is None:
                result["error"]={"stage":"paper_validation","code":"NO_VALID_PAPER_METADATA","message":"Discovered metadata did not pass scholarly-paper validation","retryable":False,"recommended_action":"Review the publication-list rules or journal identifiers"}
                if result["status"]=="temporarily_failed":result["status"]="partial"
            if metadata:
                result["last_cursor"]=metadata[0].doi or metadata[0].source_url
                dates=[normalize_date(x.publication_date) for x in metadata];dates=[x for x in dates if x]
                result["last_seen_publication_date"]=max(dates).isoformat() if dates else None
            relevant=[];uncertain=[]
            for item in metadata:
                rel=classify_relevance(item)
                if rel.status=="relevant":relevant.append((item,rel))
                elif rel.status=="uncertain":uncertain.append((item,rel))
                else:result["articles_excluded"]+=1
            result["articles_relevant"]=len(relevant);result["articles_uncertain"]=len(uncertain);relevant_to_save=relevant[:limits["relevant_papers"]]
            with self.sessions.begin() as session:
                repo=LiteratureRepository();run=session.get(__import__("sleep_ai_scientist.literature_db.models",fromlist=["UpdateRun"]).UpdateRun,run_id)
                if limits.get("sample_one_article") and metadata:
                    item=next((x for x in metadata if (x.raw_metadata or {}).get("_web_search")),next((x for x in metadata if x.discovery_channel=="publisher_api"),next((x for x in metadata if x.discovery_channel=="web_crawl"),metadata[0])));rel=classify_relevance(item)
                    c,n,m=self._ingest(session,repo,run,journal,item,rel,force_canonical=True);result["candidates_created"]+=c;result["papers_created"]+=n;result["papers_matched"]+=m;result["sample_article_saved"]=1;result["sample_discovery_channel"]=item.discovery_channel;result["sample_discovery_provider"]="web_search" if (item.raw_metadata or {}).get("_web_search") else item.discovery_provider
                else:
                    for item,rel in [*relevant_to_save,*uncertain]:
                        c,n,m=self._ingest(session,repo,run,journal,item,rel);result["candidates_created"]+=c;result["papers_created"]+=n;result["papers_matched"]+=m
            restricted={"blocked_by_robots","blocked_by_anti_bot","login_required","partial"}
            if result["status"] not in restricted:
                if relevant:result["status"]="completed_with_relevant_papers" if result["papers_created"] else "completed_no_new_papers"
                else:result["status"]="completed_no_relevant_papers"
        except Exception as exc:
            if result["status"]=="temporarily_failed":result["status"]="temporarily_failed"
            result["error"]={"journal_key":journal.journal_key,"journal_title":journal.title,"publisher":journal.publisher,"adapter":profile.adapter_name,"stage":"crawl","url":profile.homepage_url,"code":type(exc).__name__,"message":str(exc),"retryable":result["status"]=="temporarily_failed","recommended_action":"Retry later or review the profile manually"}
        return self._finish_one(journal,crawl_id,result)

    def _finish_one(self,journal,crawl_id,result):
        with self.sessions.begin() as session:
            row=session.get(JournalCrawlRun,crawl_id);row.completed_at=datetime.now(timezone.utc);row.status=result["status"]
            for key in ("listing_pages_requested","listing_pages_succeeded","article_pages_requested","article_pages_succeeded","articles_discovered","articles_parsed","articles_relevant","articles_uncertain","articles_excluded","candidates_created","papers_created","papers_matched"):setattr(row,key,result[key])
            row.robots_status=result["robots"];row.http_status_counts=result["http_status_counts"];row.errors=[result["error"]] if result["error"] else []
            state=session.get(JournalScanState,journal.journal_key);state.last_attempted_at=datetime.now(timezone.utc);state.status=result["status"]
            state.last_cursor=result.get("last_cursor")
            if result.get("last_seen_publication_date"):state.last_seen_publication_date=date.fromisoformat(result["last_seen_publication_date"])
            if result["status"] in {"completed_with_relevant_papers","completed_no_relevant_papers","completed_no_new_papers"}:state.last_successful_scan_at=datetime.now(timezone.utc);state.consecutive_failure_count=0;state.last_error=None
            else:state.consecutive_failure_count+=1;state.last_error=result["error"]
            profile=session.get(JournalScraperProfile,row.scraper_profile_id)
            if result["status"] in {"completed_with_relevant_papers","completed_no_relevant_papers","completed_no_new_papers"}:profile.last_successful_crawl_at=datetime.now(timezone.utc)
            else:profile.last_error=result["error"]
        return result

    def _safe_scan(self,item,profile,run_id,limits):
        try:return self._scan_one(item.journal,profile,run_id,limits,item.since,item.until)
        except Exception as exc:
            journal=item.journal;error={"journal_key":journal.journal_key,"journal_title":journal.title,"publisher":journal.publisher,"adapter":profile.adapter_name,"stage":"unhandled_journal","url":profile.homepage_url,"code":type(exc).__name__,"message":str(exc),"retryable":True,"recommended_action":"Retry this journal; other journals continued"}
            with self.sessions.begin() as session:
                row=JournalCrawlRun(update_run_id=run_id,journal_key=journal.journal_key,scraper_profile_id=profile.scraper_profile_id,status="temporarily_failed",completed_at=datetime.now(timezone.utc),errors=[error]);session.add(row)
                state=session.get(JournalScanState,journal.journal_key);state.status="temporarily_failed";state.last_attempted_at=datetime.now(timezone.utc);state.last_error=error;state.consecutive_failure_count+=1
            return {"journal_key":journal.journal_key,"journal":journal.title,"issn":"/".join(filter(None,[journal.issn,journal.eissn])),"publisher":journal.publisher,"adapter":profile.adapter_name,"official_url":profile.homepage_url,"primary_method":"web_search","fallback_method":"publisher_native","publisher_native_urls":[],"html_page_status":"request_failed","search_form_status":"not_checked","search_form":None,"search_queries_attempted":[],"search_result_urls":[],"search_pages_requested":0,"search_pages_succeeded":0,"robots":None,"listing_pages_requested":0,"listing_pages_succeeded":0,"article_pages_requested":0,"article_pages_succeeded":0,"http_status_counts":{},"articles_discovered":0,"articles_parsed":0,"articles_relevant":0,"articles_uncertain":0,"articles_excluded":0,"candidates_created":0,"papers_created":0,"papers_matched":0,"last_cursor":None,"last_seen_publication_date":None,"status":"temporarily_failed","error":error}

    def crawl_all(self,*,limit_journals=None,journal_key=None,resume=False,retry_failed=False,dry_run=False,since=None,until=None,**overrides):
        lock=self.engine.connect();acquired=lock.execute(text("SELECT pg_try_advisory_lock(hashtext('literature_journal_full_scan'))")).scalar_one()
        if not acquired:lock.close();raise RuntimeError("Another literature_journal_full_scan writer is already running")
        try:
            selected=[x for x in self.journals if not journal_key or x.journal_key==journal_key]
            if overrides.get("access_failures_only"):
                with self.sessions() as session:
                    access_failed={
                        row.journal_key for row in session.scalars(select(JournalScanState))
                        if row.status in {"blocked_by_robots","blocked_by_anti_bot","login_required"}
                        or (row.last_error or {}).get("code") in {"ANTI_BOT_BLOCK","LOGIN_REQUIRED"}
                        or (
                            row.status=="partial"
                            and (row.last_error or {}).get("code") in {
                                "HTTP_REQUEST_FAILED","LISTING_URL_NOT_RESOLVED",
                                "NO_VALID_PAPER_METADATA","ROBOTS_UNAVAILABLE",
                            }
                        )
                    }
                selected=[x for x in selected if x.journal_key in access_failed]
            if overrides.get("only_missing_samples"):
                with self.sessions() as session:sampled={x for x in session.scalars(select(CandidateRecord.target_journal_key).where(CandidateRecord.target_journal_key.is_not(None)))}
                selected=[x for x in selected if x.journal_key not in sampled]
            if journal_key and not selected:raise ValueError(f"Unknown journal_key: {journal_key}")
            with self.sessions() as session:states={x.journal_key:x for x in session.scalars(select(JournalScanState))}
            if overrides.get("web_search_audit_incomplete_only"):
                selected=[x for x in selected if x.journal_key in states and states[x.journal_key].status in {"partial","temporarily_failed"}]
            for journal in selected:
                if journal.journal_key in states and states[journal.journal_key].publisher:journal.publisher=states[journal.journal_key].publisher
            planning_states={} if overrides.get("only_missing_samples") or overrides.get("access_failures_only") or overrides.get("web_search_audit_all") or overrides.get("web_search_audit_incomplete_only") else states
            plan=build_scan_plan(selected,planning_states,self.crawl,limit_journals=limit_journals,since=since,until=until,resume=resume,retry_failed=retry_failed)
            if dry_run:return {"dry_run":True,"target_journals":len(self.journals),"planned_journals":len(plan),"journal_keys":[x.journal.journal_key for x in plan]}
            with self.sessions.begin() as session:run=LiteratureRepository().create_update_run(session,UpdateRunCreate(run_type="target_journal_scan",status="running",config_snapshot=self.crawl));run_id=run.run_id
            registry=JournalCrawlerRegistry(self.profile_dir);limits={"listing_pages":overrides.get("listing_pages") or self.crawl["per_journal"]["listing_pages"],"article_pages":overrides.get("article_pages") or self.crawl["per_journal"]["article_pages"],"relevant_papers":overrides.get("relevant_papers") or self.crawl["per_journal"]["relevant_papers"],"search_queries":int(overrides.get("search_queries") or 1),"sample_one_article":bool(overrides.get("sample_one_article"))};jobs=[]
            for item in plan:
                with self.sessions() as session:profile=session.scalar(select(JournalScraperProfile).where(JournalScraperProfile.journal_key==item.journal.journal_key))
                if profile is None:
                    self.build_profiles();
                    with self.sessions() as session:profile=session.scalar(select(JournalScraperProfile).where(JournalScraperProfile.journal_key==item.journal.journal_key))
                jobs.append((item,profile))
            workers=int(overrides.get("journal_workers") or self.crawl["concurrency"].get("journal_workers",4))
            if workers>1:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=workers) as executor:results=list(executor.map(lambda job:self._safe_scan(job[0],job[1],run_id,limits),jobs))
            else:results=[self._safe_scan(item,profile,run_id,limits) for item,profile in jobs]
            with self.sessions.begin() as session:
                run=session.get(__import__("sleep_ai_scientist.literature_db.models",fromlist=["UpdateRun"]).UpdateRun,run_id);LiteratureRepository().complete_update_run(session,run,status="completed" if len(results)==len(plan) else "partial",counts=dict(Counter(x["status"] for x in results)))
                snapshot=LiteratureRepository().row_counts(session)
                profiles=[{"journal_key":p.journal_key,"adapter":{"name":p.adapter_name},"verification_status":p.verification_status,"homepage_url":p.homepage_url,"latest_articles_url":p.latest_articles_url,"current_issue_url":p.current_issue_url,"rss_url":p.rss_url,"sitemap_url":p.sitemap_url} for p in session.scalars(select(JournalScraperProfile))]
            payload=build_report(self.csv_stats,self.journals,results,profiles,snapshot,planned_journals=[x.journal for x in plan])
            if limits.get("sample_one_article") and sum(x.get("sample_article_saved",0) for x in results)<len(results):
                payload["overall_result"]="PARTIAL_PASS"
            payload["report_paths"]=write_report(payload,resolve_path(self.crawl["report_dir"],self.root));return payload
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(hashtext('literature_journal_full_scan'))"));lock.close()

    def status(self):
        with self.sessions() as session:
            states=list(session.scalars(select(JournalScanState)));profiles=list(session.scalars(select(JournalScraperProfile)));runs=list(session.scalars(select(JournalCrawlRun).order_by(JournalCrawlRun.created_at)));counts=Counter(x.status for x in states)
            latest_runs={run.journal_key:run for run in runs};runs=list(latest_runs.values())
            return {"total_target_journals":len(self.journals),"profiles_created":len(profiles),"verified":sum(x.verification_status=="verified" for x in profiles),"partial":sum(x.verification_status=="partial" for x in profiles),"manual_review":sum(x.verification_status=="manual_review" for x in profiles),"blocked":sum(counts[x] for x in ("blocked_by_robots","blocked_by_anti_bot","login_required")),"completed":sum(counts[x] for x in ("completed_with_relevant_papers","completed_no_relevant_papers","completed_no_new_papers")),"failed":sum(counts[x] for x in ("temporarily_failed","permanently_failed","profile_broken")),"pending":len(self.journals)-len(states),"currently_running":sum(x.status=="running" for x in runs),"relevant_papers_found":sum(x.articles_relevant for x in runs),"candidates_created":sum(x.candidates_created for x in runs),"papers_created":sum(x.papers_created for x in runs),"papers_matched":sum(x.papers_matched for x in runs)}
