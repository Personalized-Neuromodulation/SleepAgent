from __future__ import annotations

from pathlib import Path
import yaml

from .base import GenericJsonLdAdapter,GenericMetaTagsAdapter,RssAtomAdapter,SitemapAdapter


ADAPTERS={x.name:x for x in (GenericJsonLdAdapter,GenericMetaTagsAdapter,RssAtomAdapter,SitemapAdapter)}


class JournalCrawlerRegistry:
    def __init__(self,profile_dir):self.profile_dir=Path(profile_dir);self._profiles={};self.reload()
    def reload(self):
        self._profiles={}
        index=self.profile_dir/"index.yaml"
        if not index.exists():return
        for item in (yaml.safe_load(index.read_text()) or {}).get("journals",[]):
            path=self.profile_dir/item["profile_path"]
            if path.exists():self._profiles[item["journal_key"]]=yaml.safe_load(path.read_text())
    def list_all_journals(self):return list(self._profiles.values())
    def list_supported_journals(self):return [p for p in self._profiles.values() if p.get("enabled")]
    def get_profile(self,journal_key):return self._profiles.get(journal_key)
    def get_crawler(self,journal_key):
        profile=self.get_profile(journal_key)
        if not profile or not profile.get("enabled"):return None
        cls=ADAPTERS.get(profile.get("adapter",{}).get("name"));return cls() if cls else None
    def validate_profile(self,journal_key):
        p=self.get_profile(journal_key);errors=[]
        if not p:errors.append("profile_missing")
        else:
            for key in ("journal_key","title","adapter","verification_status","enabled"):
                if key not in p:errors.append(f"missing:{key}")
            if p.get("enabled") and p.get("adapter",{}).get("name") not in ADAPTERS:errors.append("unknown_adapter")
        return {"valid":not errors,"errors":errors}
