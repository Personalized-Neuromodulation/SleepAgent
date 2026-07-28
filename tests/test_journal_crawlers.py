from __future__ import annotations

import json
from datetime import date,datetime,timezone
from pathlib import Path
from types import SimpleNamespace

from sleep_ai_scientist.literature_db.journal_crawlers.http_client import CrawlHTTPClient,DomainRateLimiter
from sleep_ai_scientist.literature_db.journal_crawlers.metadata_parser import discover_html_links,discover_search_forms,parse_article_html,parse_feed,parse_feed_metadata,parse_jats_xml,parse_sitemap,render_search_url
from sleep_ai_scientist.literature_db.journal_crawlers.models import CrawledPaperMetadata,ScraperProfileData
from sleep_ai_scientist.literature_db.journal_crawlers.paper_validation import assess_paper_metadata
from sleep_ai_scientist.literature_db.journal_crawlers.planner import build_scan_plan
from sleep_ai_scientist.literature_db.journal_crawlers.profiles import make_profile,write_profiles
from sleep_ai_scientist.literature_db.journal_crawlers.registry import JournalCrawlerRegistry
from sleep_ai_scientist.literature_db.journal_crawlers.relevance import classify_relevance
from sleep_ai_scientist.literature_db.journal_crawlers.reporting import build_report
from sleep_ai_scientist.literature_db.journal_crawlers.url_resolver import JournalURLResolver
from sleep_ai_scientist.literature_db.journal_crawlers.robots import RobotsCache
from sleep_ai_scientist.literature_db.journal_crawlers.publisher_native import publisher_native_entries
from sleep_ai_scientist.literature_db.target_journals import TargetJournal,TargetJournalLoader


def journal(key,title="Sleep Journal",issn="1234-567X"):
    return TargetJournal(key,title,title.casefold(),issn,None,"Shared Publisher",source_row_numbers=[2],raw_records=[{}])


def crawl_config():return {"publication_window":{"lookback_days":365,"overlap_days":30}}


def test_real_csv_all_valid_journals_enter_unlimited_plan():
    loader=TargetJournalLoader("data/external/2025_Q1_IF_5.csv");journals=loader.load();plan=build_scan_plan(journals,{},crawl_config())
    assert loader.stats["row_count"]==458
    assert len(journals)==len(plan)==458
    assert all(x.official_url and x.url_validation_status=="metadata_validated" for x in journals)


def test_title_only_and_deduplicated_journals_enter_plan(tmp_path):
    p=tmp_path/"journals.csv";p.write_text("Journal title,ISSN,eISSN\nTitle Only,,\nSame,1234-567X,\nSame,,1234-567X\n")
    loader=TargetJournalLoader(p);journals=loader.load();plan=build_scan_plan(journals,{},crawl_config())
    assert len(journals)==len(plan)==2
    assert any(x.journal.identifier_quality=="title_only" for x in plan)


def test_resume_and_retry_rules():
    journals=[journal("a"),journal("b"),journal("c")];now=datetime.now(timezone.utc)
    states={"a":SimpleNamespace(status="completed_no_relevant_papers",last_attempted_at=now,last_successful_scan_at=now),"b":SimpleNamespace(status="temporarily_failed",last_attempted_at=now,last_successful_scan_at=None)}
    plan=build_scan_plan(journals,states,crawl_config(),resume=True,retry_failed=True,until=date.today())
    assert [x.journal.journal_key for x in plan]==["b","c"]


def test_resume_skips_non_retryable_terminal_states():
    state=SimpleNamespace(status="blocked_by_robots",last_attempted_at=datetime.now(timezone.utc),last_successful_scan_at=None,last_error={"retryable":False})
    assert build_scan_plan([journal("a")],{"a":state},crawl_config(),resume=True,retry_failed=True)==[]


def test_single_journal_report_uses_selected_plan_size():
    result={"status":"completed_no_relevant_papers","adapter":"generic_jsonld"}
    payload=build_report({"row_count":790},[journal("a"),journal("b")],[result],[],{},planned_journals=[journal("a")])
    assert payload["summary"]["valid_deduplicated_journals"]==2
    assert payload["summary"]["journals_planned"]==1
    assert payload["overall_result"]=="PASS"


def test_profiles_include_unresolved_and_share_adapter(tmp_path):
    unresolved=make_profile(journal("none"),[],{},None)
    url=lambda key:SimpleNamespace(url_type="homepage",url="https://publisher.example/journal",is_active=True,is_official=True,requires_manual_review=False)
    first=make_profile(journal("one"),[url("one")],{},None);second=make_profile(journal("two"),[url("two")],{},None)
    index=write_profiles(tmp_path,[unresolved,first,second]);registry=JournalCrawlerRegistry(tmp_path)
    assert len(index)==len(registry.list_all_journals())==3
    assert unresolved.enabled is False and unresolved.verification_status=="manual_review"
    assert first.adapter_name==second.adapter_name=="generic_jsonld"
    assert registry.get_crawler("one").name=="generic_jsonld"


def test_profile_rejects_unverified_publisher_root():
    row=SimpleNamespace(url_type="homepage",url="https://publisher.example/",is_active=True,is_official=False,requires_manual_review=True)
    profile=make_profile(journal("one"),[row],{},None)
    assert profile.enabled is False and profile.verification_status=="manual_review"


def test_openalex_issn_and_title_identity_verifies_journal_homepage(tmp_path):
    class HTTP:
        def get(self,url):
            if "openalex" in url:
                body={"display_name":"Sleep Journal","homepage_url":"https://publisher.example/journal/sleep","issn":["1234-567X"],"host_organization_name":"Publisher"}
            else:body={"message":{"items":[{"publisher":"Publisher","resource":{"primary":{"URL":"https://publisher.example/article/1"}}}]}}
            return 200,json.dumps(body).encode(),url,{}
    urls,_,error=JournalURLResolver(HTTP(),tmp_path).resolve(journal("one"))
    homepage=next(x for x in urls if x.url_type=="homepage")
    assert homepage.is_official is True and homepage.url.endswith("/journal/sleep") and error is None
    assert next(x for x in urls if x.url_type=="article_entry").url.endswith("/article/1")


def test_openalex_title_mismatch_requires_manual_review(tmp_path):
    class HTTP:
        def get(self,url):
            if "openalex" in url:
                body={"display_name":"Unrelated Chemistry Review","homepage_url":"https://publisher.example/","issn":["1234-567X"]}
            else:body={"message":{"items":[]}}
            return 200,json.dumps(body).encode(),url,{}
    urls,_,error=JournalURLResolver(HTTP(),tmp_path).resolve(journal("one"))
    homepage=next(x for x in urls if x.url_type=="homepage")
    assert homepage.is_official is False and homepage.requires_manual_review is True
    assert error["code"]=="JOURNAL_IDENTITY_MISMATCH"


def test_profile_manual_rules_survive_refresh(tmp_path):
    profile=ScraperProfileData("one","One",None,"generic_jsonld",verification_status="partial",enabled=True,homepage_url="https://example.org",discovery_rules={"manual_override":True,"selector":".old"})
    write_profiles(tmp_path,[profile]);profile.discovery_rules={"selector":".new"};write_profiles(tmp_path,[profile])
    assert JournalCrawlerRegistry(tmp_path).get_profile("one")["discovery_rules"]["selector"]==".old"


def test_jsonld_and_citation_metadata_parsing():
    html='''<html><head><meta name="citation_title" content="Fallback"><meta name="citation_doi" content="10.1/test"><script type="application/ld+json">{"@type":"ScholarlyArticle","headline":"Sleep and resting-state fMRI","abstract":"Sleep quality study","author":[{"givenName":"A","familyName":"B"}],"datePublished":"2025-01-02","isPartOf":{"name":"Journal"}}</script></head></html>'''
    row=parse_article_html(html,"https://example.org/a");assert row.title=="Sleep and resting-state fMRI" and row.doi=="10.1/test" and row.authors[0]["family_name"]=="B"
    assert classify_relevance(row).status=="relevant"


def test_jsonld_schema_type_array_is_supported():
    html='''<script type="application/ld+json">{"@type":["Article","NewsArticle"],"headline":"Sleep and circadian timing"}</script>'''
    row=parse_article_html(html,"https://example.org/a")
    assert row is not None and row.title=="Sleep and circadian timing" and row.article_type=="Article"


def test_homepage_canonical_is_not_an_article_or_publication_list():
    html='''<head><link rel="canonical" href="https://example.org/journal/sleep"></head>
    <body><a href="/about">About the journal</a></body>'''
    links=discover_html_links(html,"https://example.org/journal/sleep")
    assert links["article"]==[] and links["listing"]==[]


def test_publication_list_and_article_links_are_distinguished():
    homepage='<a href="/journal/sleep/latest">Latest articles</a>'
    listing='<a href="/article/10.1/sleep-001">Sleep study title</a><a href="/journal/sleep">Journal home</a>'
    assert discover_html_links(homepage,"https://example.org")["listing"]==["https://example.org/journal/sleep/latest"]
    assert discover_html_links(listing,"https://example.org")["article"]==["https://example.org/article/10.1/sleep-001"]


def test_search_form_is_discovered_and_rendered_with_hidden_journal_scope():
    html='''<form role="search" action="/search" method="get">
    <input type="hidden" name="publication" value="sleep-journal">
    <input name="qs" placeholder="Search in this journal"><button>Search</button></form>'''
    forms=discover_search_forms(html,"https://publisher.example/journal/sleep")
    assert len(forms)==1 and forms[0]["query_field"]=="qs" and forms[0]["supported"]
    assert render_search_url(forms[0]["url_template"],"sleep apnea")=="https://publisher.example/search?publication=sleep-journal&qs=sleep+apnea"


def test_paper_validation_rejects_journal_homepage_issue_and_editorial_board():
    target=journal("sleep")
    rows=[
        CrawledPaperMetadata("https://example.org/journal/sleep","Sleep Journal",journal="Sleep Journal"),
        CrawledPaperMetadata("https://example.org/content/12/3","Sleep Journal, Volume 12, Issue 3",journal="Sleep Journal"),
        CrawledPaperMetadata("https://doi.org/10.1/board","Editorial Board",journal="Sleep Journal",doi="10.1/board",publication_date="2026-01-01",article_type="journal-article",raw_metadata={"ISSN":["1234-567X"]}),
        CrawledPaperMetadata("https://doi.org/10.1/erratum","Erratum: A previously published paper",journal="Sleep Journal",doi="10.1/erratum",publication_date="2026-01-01",article_type="journal-article",raw_metadata={"ISSN":["1234-567X"]}),
        CrawledPaperMetadata("https://doi.org/10.1/correction","Author Correction: A previously published paper",journal="Sleep Journal",doi="10.1/correction",publication_date="2026-01-01",article_type="journal-article",raw_metadata={"ISSN":["1234-567X"]}),
        CrawledPaperMetadata("https://doi.org/10.1/concern","EXPRESSION OF CONCERN: A previously published paper",journal="Sleep Journal",doi="10.1/concern",publication_date="2026-01-01",article_type="journal-article",raw_metadata={"ISSN":["1234-567X"]}),
        CrawledPaperMetadata("https://doi.org/10.1/response","Original article title. Response to earlier correspondence",journal="Sleep Journal",doi="10.1/response",publication_date="2026-01-01",article_type="journal-article",raw_metadata={"ISSN":["1234-567X"]}),
    ]
    assert all(not assess_paper_metadata(row,target).is_paper for row in rows)


def test_paper_validation_requires_article_level_and_bibliographic_evidence():
    target=journal("sleep")
    weak=CrawledPaperMetadata("https://example.org/page","A sufficiently long promotional page title",journal="Sleep Journal",publication_date="2026-01-01")
    paper=CrawledPaperMetadata(
        "https://doi.org/10.1/paper","Effects of sleep restriction on cognition",
        authors=[{"family_name":"Smith"}],journal="Sleep Journal",
        publication_date="2026-01-01",doi="10.1/paper",article_type="journal-article",
        raw_metadata={"ISSN":["1234-567X"]},
    )
    assert assess_paper_metadata(weak,target).is_paper is False
    assessment=assess_paper_metadata(paper,target)
    assert assessment.is_paper is True and assessment.evidence["journal_identity"] is True


def test_crossref_title_markup_is_removed_before_validation(tmp_path):
    row=JournalURLResolver(None,tmp_path).item_to_metadata({
        "title":["Self-poisoning with <scp>NSW</scp> clinical data"],
        "container-title":["Sleep Journal"],"author":[{"family":"Smith"}],
        "published":{"date-parts":[[2026,1,1]]},"DOI":"10.1/paper",
        "type":"journal-article","ISSN":["1234-567X"],
    })
    assert row.title=="Self-poisoning with NSW clinical data"
    assert assess_paper_metadata(row,journal("sleep")).is_paper is True


def test_citation_metadata_can_validate_article_without_jsonld_type():
    html='''<head>
      <meta name="citation_title" content="Sleep timing and brain connectivity">
      <meta name="citation_author" content="Jane Smith">
      <meta name="citation_journal_title" content="Sleep Journal">
      <meta name="citation_publication_date" content="2026-01-01">
    </head>'''
    row=parse_article_html(html,"https://example.org/article/1")
    assert row is not None and assess_paper_metadata(row,journal("sleep")).is_paper is True


def test_rss_and_sitemap_parsing():
    assert parse_feed('<rss><channel><item><link>https://x/article/1</link></item></channel></rss>')==["https://x/article/1"]
    assert parse_sitemap('<urlset><url><loc>https://x/article/2</loc></url></urlset>')==["https://x/article/2"]


def test_feed_ignores_channel_link_and_jats_is_article_metadata():
    assert parse_feed('<rss><channel><link>https://x/home</link><item><link>https://x/article/1</link></item></channel></rss>')==["https://x/article/1"]
    xml='''<article article-type="research-article"><front><journal-meta><journal-title>Sleep Journal</journal-title></journal-meta><article-meta>
    <article-id pub-id-type="doi">10.1234/sleep.2</article-id><title-group><article-title>Sleep timing and cognition in adults</article-title></title-group>
    <contrib-group><contrib contrib-type="author"><name><surname>Smith</surname><given-names>Jane</given-names></name></contrib></contrib-group>
    <pub-date><day>2</day><month>1</month><year>2026</year></pub-date></article-meta></front></article>'''
    row=parse_jats_xml(xml,"https://publisher.example/article/xml")
    assert row.doi=="10.1234/sleep.2" and assess_paper_metadata(row,journal("sleep")).is_paper


def test_publisher_feed_metadata_is_a_valid_direct_web_record():
    xml='''<rss xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/"><channel>
    <prism:publicationName>Sleep Journal</prism:publicationName><item>
    <title>Effects of sleep restriction on cognition</title><link>https://publisher.example/doi/10.1234/sleep.1</link>
    <dc:date>2026-01-02</dc:date><dc:creator>Jane Smith</dc:creator>
    <prism:doi>10.1234/sleep.1</prism:doi><prism:section>Research Article</prism:section>
    </item></channel></rss>'''
    row=parse_feed_metadata(xml)[0]
    assert row.discovery_provider=="publisher_feed"
    assert assess_paper_metadata(row,journal("sleep")).is_paper is True


def test_native_publisher_entries_are_derived_without_crossref():
    assert publisher_native_entries("https://onlinelibrary.wiley.com/journal/13265377")==[
        ("rss","https://onlinelibrary.wiley.com/feed/13265377/most-recent")
    ]
    assert publisher_native_entries("https://link.springer.com/journal/11427")==[
        ("listing","https://link.springer.com/journal/11427/articles")
    ]
    assert publisher_native_entries("https://mental.jmir.org/")[0][1].startswith("https://mental.jmir.org/20")
    assert publisher_native_entries("https://insight.jci.org/")==[
        ("rss","https://insight.jci.org/rss")
    ]


def test_domain_rate_limiter_shares_domain_and_separates_domains():
    clock=[10.0];slept=[]
    def now():return clock[0]
    def sleep(seconds):slept.append(seconds);clock[0]+=seconds
    limiter=DomainRateLimiter(1,sleep_fn=sleep,clock=now);limiter.wait("https://same.example/a");limiter.wait("https://same.example/b");before=len(slept);limiter.wait("https://other.example/a")
    assert slept and len(slept)==before


def test_retry_after_and_robots_cache_behavior():
    class HTTP:
        def __init__(self):self.calls=0
        def get(self,url):self.calls+=1;return 200,b"User-agent: *\nDisallow: /private\n",url,{}
    http=HTTP();robots=RobotsCache(http)
    assert robots.check("https://example.org/public")==('allowed',True)
    assert robots.check("https://example.org/private/x")==('disallowed',False)
    assert http.calls==1


def test_robots_supports_wildcards_end_anchors_and_longest_allow():
    class HTTP:
        def get(self,url):
            body=b"User-agent: *\nDisallow: /\nAllow: /journal*\nAllow: /$\n"
            return 200,body,url,{}
    robots=RobotsCache(HTTP())
    assert robots.check("https://example.org/journal/11427")==("allowed",True)
    assert robots.check("https://example.org/")==("allowed",True)
    assert robots.check("https://example.org/private")==("disallowed",False)


def test_http_client_respects_retry_after(tmp_path):
    class Response:
        def __init__(self,status,headers=None):self.status_code=status;self.headers=headers or {};self.content=b"ok";self.url="https://retry.example/x"
    class Session:
        def __init__(self):self.headers={};self.calls=0
        def get(self,*args,**kwargs):self.calls+=1;return Response(429,{"Retry-After":"2"}) if self.calls==1 else Response(200)
    slept=[];session=Session();client=CrawlHTTPClient(tmp_path,{"requests_per_second_per_domain":1000,"timeout_seconds":1,"max_retries":1,"respect_retry_after":True},session=session,sleep_fn=slept.append)
    status,body,_,_=client.get("https://retry.example/x",use_cache=False)
    assert status==200 and body==b"ok" and any(x>=2 for x in slept)


def test_no_global_stop_after_first_success_or_failure():
    journals=[journal(str(i)) for i in range(4)];visited=[]
    for item in build_scan_plan(journals,{},crawl_config()):
        visited.append(item.journal.journal_key)
        try:
            if item.journal.journal_key=="1":raise RuntimeError("single journal failure")
        except RuntimeError:continue
    assert visited==["0","1","2","3"]
