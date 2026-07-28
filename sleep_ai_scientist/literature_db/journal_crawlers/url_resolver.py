from __future__ import annotations

import json
import html as html_lib
import re
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from ..normalization import normalize_issn, normalize_journal
from .models import CrawledPaperMetadata, ResolvedJournalURL


def _clean_metadata_text(value):
    if value is None:
        return None
    return " ".join(re.sub(r"<[^>]+>", " ", html_lib.unescape(str(value))).split())


def normalize_url(value:str)->str:
    p=urlsplit(value.strip());return urlunsplit((p.scheme.casefold(),p.netloc.casefold(),p.path.rstrip("/") or "/",p.query,""))


class JournalURLResolver:
    def __init__(self,http_client,cache_dir,mailto=""):
        self.http=http_client;self.cache_dir=Path(cache_dir)/"resolution";self.cache_dir.mkdir(parents=True,exist_ok=True);self.mailto=mailto
    def _api_url(self,journal,rows=20,from_date=None,until=None):
        issn=journal.issn or journal.eissn;filters=[]
        if from_date:filters.append(f"from-pub-date:{from_date}")
        if until:filters.append(f"until-pub-date:{until}")
        params=f"rows={rows}&sort=published&order=desc"
        if filters:params+=f"&filter={','.join(filters)}"
        if self.mailto:params+=f"&mailto={quote(self.mailto)}"
        return f"https://api.crossref.org/journals/{quote(issn or '')}/works?{params}"
    def fetch_crossref(self,journal,rows=20,lookback_days=365,from_date=None,until=None):
        end=until or date.today();start=from_date or end-timedelta(days=lookback_days)
        url=self._api_url(journal,rows,start.isoformat(),end.isoformat())
        status,body,final,_=self.http.get(url)
        if status!=200:raise RuntimeError(f"Crossref returned HTTP {status}")
        payload=json.loads(body);return payload.get("message",{}).get("items",[]),final

    def fetch_openalex_works(self,journal,rows=5):
        results=[]
        for issn in dict.fromkeys(x for x in (journal.issn,journal.eissn) if x):
            url=f"https://api.openalex.org/works?filter=primary_location.source.issn:{quote(issn)}&sort=publication_date:desc&per-page={rows}"
            if self.mailto:url+=f"&mailto={quote(self.mailto)}"
            status,body,_,_=self.http.get(url)
            if status!=200:continue
            results.extend(json.loads(body).get("results",[]))
            if results:break
        return results[:rows]

    def fetch_crossref_works_by_issn(self,journal,rows=5):
        results=[]
        for issn in dict.fromkeys(x for x in (journal.issn,journal.eissn) if x):
            url=f"https://api.crossref.org/works?filter=issn:{quote(issn)}&rows={rows}&sort=published&order=desc"
            if self.mailto:url+=f"&mailto={quote(self.mailto)}"
            status,body,_,_=self.http.get(url)
            if status!=200:continue
            results.extend(json.loads(body).get("message",{}).get("items",[]))
            if results:break
        return results[:rows]

    def fetch_europe_pmc_works(self,journal,rows=5):
        results=[]
        for issn in dict.fromkeys(x for x in (journal.issn,journal.eissn) if x):
            url=f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=ISSN:{quote(issn)}&format=json&pageSize={rows}&sort_date:y"
            status,body,_,_=self.http.get(url)
            if status!=200:continue
            results.extend(json.loads(body).get("resultList",{}).get("result",[]))
            if results:break
        return results[:rows]

    @staticmethod
    def openalex_item_to_metadata(item):
        authors=[]
        for authorship in item.get("authorships") or []:
            author=authorship.get("author") or {};name=author.get("display_name") or "";bits=name.split()
            authors.append({"given_name":" ".join(bits[:-1]) or None,"family_name":bits[-1] if bits else None,"orcid":author.get("orcid"),"raw":authorship})
        location=item.get("primary_location") or {};source=location.get("source") or {};ids=item.get("ids") or {}
        concepts=[x.get("display_name") for x in item.get("concepts") or [] if x.get("display_name")]
        pmid=(ids.get("pmid") or "").rstrip("/").rsplit("/",1)[-1] or None
        pmcid=(ids.get("pmcid") or "").rstrip("/").rsplit("/",1)[-1] or None
        return CrawledPaperMetadata(source_url=location.get("landing_page_url") or item.get("doi") or item.get("id") or "",title=item.get("title") or item.get("display_name") or "",authors=authors,abstract=None,journal=source.get("display_name"),publication_date=item.get("publication_date"),doi=item.get("doi"),pmid=pmid,pmcid=pmcid,article_type=item.get("type"),language=item.get("language"),keywords=concepts,raw_metadata=item,discovery_channel="api_fallback",discovery_provider="openalex")

    @staticmethod
    def europe_pmc_item_to_metadata(item):
        authors=[]
        for author in (item.get("authorList") or {}).get("author") or []:
            name=author.get("fullName") or "";bits=name.split()
            authors.append({"given_name":" ".join(bits[:-1]) or None,"family_name":bits[-1] if bits else None,"orcid":author.get("authorId"),"raw":author})
        return CrawledPaperMetadata(source_url=item.get("doi") and f"https://doi.org/{item['doi']}" or item.get("pmid") and f"https://pubmed.ncbi.nlm.nih.gov/{item['pmid']}/" or "",title=item.get("title") or "",authors=authors,abstract=None,journal=item.get("journalTitle"),publication_date=item.get("firstPublicationDate") or item.get("firstIndexDate"),doi=item.get("doi"),pmid=item.get("pmid"),pmcid=item.get("pmcid"),article_type=item.get("pubType"),raw_metadata=item,discovery_channel="api_fallback",discovery_provider="europe_pmc")

    @staticmethod
    def _title_matches(expected, actual):
        left=normalize_journal(expected);right=normalize_journal(actual)
        if not left or not right:return False,0.0
        if left==right or left in right or right in left:return True,1.0
        score=SequenceMatcher(None,left,right).ratio()
        left_tokens=set(left.split())-{"the","of","and","journal"};right_tokens=set(right.split())-{"the","of","and","journal"}
        token_score=len(left_tokens & right_tokens)/max(1,len(left_tokens | right_tokens))
        combined=max(score,token_score)
        return combined>=0.72,combined

    def _openalex_source(self,journal):
        errors=[]
        expected={normalize_issn(x) for x in (journal.issn,journal.eissn) if x}
        for issn in (journal.issn,journal.eissn):
            if not issn:continue
            try:
                url=f"https://api.openalex.org/sources/issn:{quote(issn)}"
                if self.mailto:url+=f"?mailto={quote(self.mailto)}"
                status,body,_,_=self.http.get(url)
                if status!=200:
                    errors.append(f"OpenAlex {issn} returned HTTP {status}");continue
                data=json.loads(body);actual={normalize_issn(x) for x in data.get("issn") or [] if x}
                identifier_match=bool(expected & actual)
                title_match,title_score=self._title_matches(journal.title,data.get("display_name") or "")
                homepage=data.get("homepage_url")
                if not homepage:
                    errors.append(f"OpenAlex {issn} has no homepage_url");continue
                verified=identifier_match and title_match
                row=ResolvedJournalURL(
                    homepage,"homepage","openalex","issn_source_homepage_identity_match",
                    round(0.7+0.28*title_score,3) if identifier_match else 0.25,
                    verified,requires_manual_review=not verified,
                    error=None if verified else {
                        "code":"JOURNAL_IDENTITY_MISMATCH",
                        "expected_title":journal.title,"actual_title":data.get("display_name"),
                        "expected_issn":sorted(expected),"actual_issn":sorted(actual),
                        "title_similarity":round(title_score,3),
                    },
                )
                return row,data.get("host_organization_name"),None if verified else row.error
            except Exception as exc:errors.append(f"OpenAlex {issn}: {exc}")
        return None,None,{"code":"JOURNAL_URL_NOT_FOUND","message":"; ".join(errors) or "No ISSN available for OpenAlex source lookup","retryable":True}

    def resolve(self,journal):
        if journal.official_url:
            status=(journal.url_validation_status or "").casefold()
            verified=status in {"metadata_validated","verified","validated"}
            error=None if verified else {"code":"CSV_URL_MANUAL_REVIEW","message":journal.url_review_reason or "CSV URL requires manual review","retryable":False}
            return [ResolvedJournalURL(journal.official_url,"homepage","target_journal_csv","csv_url_validation",1.0 if verified else 0.5,verified,requires_manual_review=not verified,error=error)],journal.publisher,error
        homepage,publisher,openalex_error=self._openalex_source(journal)
        crossref_error=None
        try:items,_=self.fetch_crossref(journal,rows=1,lookback_days=3650)
        except Exception as exc:items=[];crossref_error=str(exc)
        urls=[homepage] if homepage else []
        if not items:
            error=None if homepage and homepage.is_official else openalex_error or {"code":"JOURNAL_URL_NOT_FOUND","message":crossref_error or "Crossref returned no recent works","retryable":bool(crossref_error)}
            return urls,publisher,error
        item=items[0];publisher=publisher or item.get("publisher");raw_url=((item.get("resource") or {}).get("primary") or {}).get("URL")
        if not raw_url:
            candidate=item.get("URL");host=urlsplit(candidate or "").netloc.casefold()
            raw_url=candidate if host and host not in {"doi.org","dx.doi.org"} else None
        if raw_url:urls.append(ResolvedJournalURL(raw_url,"article_entry","crossref","resource_primary",0.9,True))
        error=None if homepage and homepage.is_official else openalex_error
        return urls,publisher,error
    @staticmethod
    def item_to_metadata(item):
        titles=item.get("title") or [];containers=item.get("container-title") or [];authors=[]
        for author in item.get("author") or []:authors.append({"given_name":author.get("given"),"family_name":author.get("family"),"orcid":author.get("ORCID"),"raw":author})
        parts=((item.get("published") or {}).get("date-parts") or [[]])[0]
        pub="-".join(str(x) for x in parts) if parts else None
        return CrawledPaperMetadata(source_url=item.get("URL") or "",title=_clean_metadata_text(titles[0] if titles else "") or "",authors=authors,abstract=item.get("abstract"),journal=containers[0] if containers else None,publication_date=pub,doi=item.get("DOI"),volume=item.get("volume"),issue=item.get("issue"),pages=item.get("page"),article_type=item.get("type"),language=item.get("language"),keywords=item.get("subject") or [],raw_metadata=item,discovery_channel="api_fallback",discovery_provider="crossref")
