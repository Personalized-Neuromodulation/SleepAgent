from __future__ import annotations

from pathlib import Path
import yaml

from .models import ScraperProfileData


def profile_filename(journal_key):return journal_key.replace(":","_")+".yaml"


def make_profile(journal,urls,request_policy,existing=None):
    if any("journal_identifier_conflict" in warning for warning in journal.warnings):
        return ScraperProfileData(journal.journal_key,journal.title,journal.publisher,"unresolved",verification_status="manual_review",enabled=False,request_policy=request_policy,last_error={"code":"JOURNAL_IDENTIFIER_CONFLICT","message":"ISSN/eISSN maps to conflicting journal titles"})
    by_type={row.url_type:row.url for row in urls if row.is_active and row.is_official and not row.requires_manual_review}
    homepage=by_type.get("homepage")
    if not homepage:
        return ScraperProfileData(journal.journal_key,journal.title,journal.publisher,"unresolved",verification_status="manual_review",enabled=False,request_policy=request_policy,last_error={"code":"JOURNAL_URL_NOT_FOUND","message":"No verified official homepage"})
    discovery=(existing or {}).get("discovery_rules",{})
    article=(existing or {}).get("article_rules",{})
    return ScraperProfileData(journal.journal_key,journal.title,journal.publisher,"generic_jsonld",verification_status="partial",enabled=True,homepage_url=homepage,latest_articles_url=by_type.get("latest_articles"),current_issue_url=by_type.get("current_issue"),archive_url=by_type.get("archive"),rss_url=by_type.get("rss"),sitemap_url=by_type.get("sitemap"),discovery_rules=discovery,article_rules=article,request_policy=request_policy,last_error=None if any(by_type.get(x) for x in ("latest_articles","current_issue","rss","sitemap")) else {"code":"LISTING_URL_NOT_RESOLVED","message":"Homepage resolved; listing discovery deferred to crawl"})


def write_profiles(profile_dir,profiles):
    root=Path(profile_dir);root.mkdir(parents=True,exist_ok=True);index=[]
    for profile in profiles:
        name=profile_filename(profile.journal_key);path=root/name
        old=yaml.safe_load(path.read_text()) if path.exists() else None
        data=profile.to_dict()
        if old:
            if (old.get("discovery_rules") or {}).get("manual_override"):data["discovery_rules"]=old["discovery_rules"]
            if (old.get("article_rules") or {}).get("manual_override"):data["article_rules"]=old["article_rules"]
        data["adapter"]={"name":data.pop("adapter_name"),"version":data.pop("adapter_version")}
        path.write_text(yaml.safe_dump(data,sort_keys=False,allow_unicode=True),encoding="utf-8")
        index.append({"journal_key":profile.journal_key,"title":profile.title,"publisher":profile.publisher,"adapter_name":data["adapter"]["name"],"verification_status":profile.verification_status,"enabled":profile.enabled,"profile_path":name})
    (root/"index.yaml").write_text(yaml.safe_dump({"journals":index},sort_keys=False,allow_unicode=True),encoding="utf-8")
    return index
