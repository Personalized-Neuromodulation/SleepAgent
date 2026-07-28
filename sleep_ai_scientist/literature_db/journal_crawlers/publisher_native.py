from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit


def publisher_native_entries(homepage_url: str, journal=None) -> list[tuple[str, str]]:
    """Return deterministic, publisher-owned discovery endpoints.

    These are public feeds/listings exposed by the publisher itself.  They are
    not metadata-aggregator fallbacks and are still checked against robots.txt
    before use.
    """

    parts = urlsplit(homepage_url)
    host = parts.netloc.casefold()
    path = parts.path.rstrip("/")
    entries: list[tuple[str, str]] = []

    if host.endswith("onlinelibrary.wiley.com"):
        match = re.search(r"/journal/([^/?#]+)", path, re.I)
        if match:
            entries.append(
                ("rss", f"{parts.scheme or 'https'}://{parts.netloc}/feed/{match.group(1)}/most-recent")
            )
        for issn in (getattr(journal, "eissn", None), getattr(journal, "issn", None)):
            if issn:
                entries.append(
                    ("rss", f"https://{parts.netloc}/feed/{issn.replace('-', '').casefold()}/most-recent")
                )

    if host == "link.springer.com":
        match = re.search(r"/journal/(\d+)", path, re.I)
        if match:
            # The journal page itself is explicitly allowed by Springer robots
            # and contains article-list links.  Keep this as a listing seed.
            entries.append(("listing", f"https://link.springer.com/journal/{match.group(1)}/articles"))

    if host.endswith(".biomedcentral.com") or host.endswith(".springeropen.com"):
        entries.append(("listing", f"{parts.scheme or 'https'}://{parts.netloc}/articles"))

    if host in {"www.ahajournals.org", "www.annualreviews.org"}:
        match = re.search(r"/journal/([^/?#]+)", path, re.I)
        if match:
            code = match.group(1)
            entries.append(
                (
                    "rss",
                    f"https://{parts.netloc}/action/showFeed?type=etoc&feed=rss&jc={code}",
                )
            )

    if host == "www.cell.com":
        match = re.match(r"/([^/]+)/(?:home|current)$", path, re.I)
        if match:
            entries.append(("rss", f"https://www.cell.com/{match.group(1)}/current.rss"))

    if host == "www.tandfonline.com":
        match = re.search(r"/toc/([^/]+)/current", path, re.I)
        if match:
            entries.append(("rss", f"https://www.tandfonline.com/feed/rss/{match.group(1)}"))
        elif re.fullmatch(r"/[a-z]{4}", path, re.I):
            code=path.strip("/").casefold()+"20"
            entries.extend([
                ("rss",f"https://www.tandfonline.com/feed/rss/{code}"),
                ("listing",f"https://www.tandfonline.com/toc/{code}/current"),
            ])

    if host == "www.jmir.org" or host.endswith(".jmir.org"):
        entries.append(("listing", f"https://{parts.netloc}/{date.today().year}"))

    if host in {"www.jci.org", "insight.jci.org"}:
        entries.append(("rss", f"https://{parts.netloc}/rss"))

    if host == "www.oaepublish.com":
        slug = path.strip("/").split("/", 1)[0]
        if slug:
            entries.append(("listing",f"https://www.oaepublish.com/{slug}/articles"))
            entries.append(("rss", f"https://f.oaes.cc/rss/{slug}.xml"))

    return list(dict.fromkeys(entries))
