# -*- coding: utf-8 -*-
from urllib.parse import quote_plus, urlparse


class PublisherStrategy:
    """Build publisher search URLs from the CSV URL host only."""

    HTTPS_SEARCH_HOSTS = (
        "nejm.org",
        "annualreviews.org",
        "sciencedirect.com",
        "oup.com",
        "academic.oup.com",
        "tandfonline.com",
        "jamanetwork.com",
    )

    def build_search_url(self, base_url, keyword, page=1):
        parsed = urlparse(base_url)
        host = (parsed.netloc or "").lower()
        scheme = "https" if host.endswith(self.HTTPS_SEARCH_HOSTS) else (parsed.scheme or "https")
        root = f"{scheme}://{parsed.netloc}" if parsed.netloc else base_url.rstrip("/")
        query = quote_plus(keyword)
        if host.endswith("sciencedirect.com"):
            return f"{root}/search?qs={query}"
        if host.endswith("onlinelibrary.wiley.com"):
            return f"{root}/action/doSearch?AllField={query}&startPage={max(0, page - 1)}"
        if host.endswith("biomedcentral.com") or host.endswith("springer.com"):
            return f"{root}/search?query={query}&page={page}"
        if host.endswith("annualreviews.org"):
            return f"{root}/search?noRedirect=true&option1=all&value1={query}&pageSize=20"
        if host.endswith("jamanetwork.com") or host.endswith("jama.ama-assn.org"):
            return f"https://jamanetwork.com/searchresults?q={query}&page={page}"
        if host.endswith("nejm.org"):
            return f"{root}/search?q={query}&page={page}"
        if host.endswith("academic.oup.com") or host.endswith("oup.com"):
            return f"{root}/search-results?page={page}&q={query}"
        if host.endswith("tandfonline.com"):
            return f"{root}/action/doSearch?AllField={query}&startPage={max(0, page - 1)}"
        return f"{root}/search?q={query}&page={page}"
