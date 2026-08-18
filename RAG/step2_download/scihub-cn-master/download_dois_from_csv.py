#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import asyncio
import csv
import logging
import os
import re
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from download import normalize_proxy


logger = logging.getLogger("download-dois-from-csv")


DOI_URL_PREFIX_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
DEFAULT_SCIHUB_ST_COOKIE = (
    "__ddg1_=sofzCNT6Zq3sQX1kugVR; "
    "__ddg10_=1786417877; "
    "__ddg8_=6cHli5bCBUgbVCiU; "
    "__ddg9_=38.49.218.25; "
    "PHPSESSID=243a755496d01973e0eca4a24871c154; "
    "refresh=1786412156.8637; "
    "session=ade309d5857fbbf5f8b397242b7106b2"
)
DEFAULT_SCIHUB_SU_COOKIE = (
    "__ddg1_=4ldVR7efAHKk8muy0PUr; "
    "__ddg10_=1786417823; "
    "__ddg8_=qNpj6JHW62xlq4lB; "
    "__ddg9_=5.34.216.87; "
    "PHPSESSID=169d9509ff21ad5877c2fbcfb6f5e11f; "
    "refresh=1786431941.2795; "
    "session=95ff7caf79409029b1b522354eedcdfb"
)
DEFAULT_SCIHUB_RED_COOKIE = (
    "__ddg1_=v7upgnMIbpZdhbBtBIVR; "
    "__ddg10_=1786417905; "
    "__ddg8_=pD5kxGV7Q8mGYNtO; "
    "__ddg9_=38.49.218.25; "
    "PHPSESSID=906ba75df06c0d4d55379545367743c9; "
    "refresh=1786417903.7015; "
    "session=029139b558d65c1fcb204fcd7533f894"
)
DEFAULT_SCIHUB_BOX_COOKIE = (
    "__ddg1_=DAY2VkKk0ZHU36vDgjaV; "
    "__ddg10_=1786417929; "
    "__ddg8_=96V0vpO69N2M3u90; "
    "__ddg9_=5.34.216.87; "
    "PHPSESSID=cec72341dd30626ee6d46e047f4b01a7; "
    "refresh=1786417928.1288; "
    "session=42797b5faa55fe1655cd97130e37cb5a"
)
DEFAULT_SCIHUB_RU_COOKIE = (
    "__ddg1_=vMFExu1kyVmIfpTyq6u0; "
    "__ddg10_=1786417951; "
    "__ddg8_=F275PyKXBZvXz1K8; "
    "__ddg9_=5.34.216.87; "
    "PHPSESSID=612814b417628dfb14559a8d821c314b; "
    "refresh=1786417446.2917; "
    "session=cae57289234919dfbfae5a8944b9a5d0"
)
DEFAULT_SCI_NET_COOKIE = (
    "__ddg1_=djoxMfCqTxEme0vYdyrB; "
    "__ddg10_=1786606159; "
    "__ddg8_=Np5DjpNZhTN2lYDi; "
    "__ddg9_=98.98.42.195; "
    "connect.sid=s%3AWJyWpNlCVns3rcDXhaCfbFTDWpaEu-ch.EOKp%2FYGb6UrxoyisSwqAwnWXybnP08gWumc7kQdaULc"
)

DEFAULT_SCIHUB_COOKIE = DEFAULT_SCIHUB_ST_COOKIE
DEFAULT_COOKIE_FILE = Path(__file__).with_name("scihub_cookies.json")
DEFAULT_MIRROR_COOKIES = {
    "sci-hub.box": DEFAULT_SCIHUB_BOX_COOKIE,
    "sci-hub.st": DEFAULT_SCIHUB_ST_COOKIE,
    "sci-hub.su": DEFAULT_SCIHUB_SU_COOKIE,
    "sci-hub.red": DEFAULT_SCIHUB_RED_COOKIE,
    "sci-hub.ru": DEFAULT_SCIHUB_RU_COOKIE,
    "sci-net.xyz": DEFAULT_SCI_NET_COOKIE,
}


def _cookie_items_to_header(items: Iterable[dict]) -> str:
    parts = []
    for item in items:
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if name and value:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def load_mirror_cookies(cookie_file: Optional[os.PathLike] = None) -> Dict[str, str]:
    """Load per-domain Sci-Hub cookies from JSON, falling back to built-ins.

    Supported JSON formats:
    1. {"sci-hub.st": "__ddg1_=...; PHPSESSID=..."}
    2. {"sci-hub.st": [{"name": "__ddg1_", "value": "..."}]}
    3. [{"domain": ".sci-hub.st", "name": "__ddg1_", "value": "..."}]
    4. {"cookies": [{"domain": ".sci-hub.st", "name": "__ddg1_", "value": "..."}]}
    """
    path = Path(cookie_file or DEFAULT_COOKIE_FILE)
    cookies = dict(DEFAULT_MIRROR_COOKIES)
    if not path.exists():
        return cookies

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load cookie file %s: %s", path, exc)
        return cookies

    loaded: Dict[str, str] = {}
    if isinstance(data, dict) and isinstance(data.get("cookies"), list):
        data = data["cookies"]

    if isinstance(data, list):
        grouped: Dict[str, List[dict]] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or item.get("host") or "").strip().lstrip(".")
            if domain:
                grouped.setdefault(domain, []).append(item)
        loaded = {domain: _cookie_items_to_header(items) for domain, items in grouped.items()}
    elif isinstance(data, dict):
        for domain, value in data.items():
            host = str(domain).strip().lstrip(".")
            if isinstance(value, str):
                loaded[host] = value.strip()
            elif isinstance(value, list):
                loaded[host] = _cookie_items_to_header(item for item in value if isinstance(item, dict))

    loaded = {domain: cookie for domain, cookie in loaded.items() if domain and cookie}
    cookies.update(loaded)
    logger.info("Loaded runtime Sci-Hub cookies for %s from %s.", ", ".join(sorted(loaded)), path)
    return cookies


def normalize_doi(value: Optional[str]) -> str:
    if value is None:
        return ""
    doi = value.strip()
    doi = re.sub(r"^doi\s*:\s*", "", doi, flags=re.IGNORECASE)
    doi = DOI_URL_PREFIX_RE.sub("", doi)
    return doi.strip()


def _match_column(fieldnames: Iterable[str], doi_column: Optional[str]) -> str:
    names = [name for name in fieldnames if name is not None]
    if doi_column:
        for name in names:
            if name.strip() == doi_column:
                return name
        raise ValueError(
            "DOI column {!r} not found. Available columns: {}".format(
                doi_column, ", ".join(names)
            )
        )

    for name in names:
        if name.strip().lower() == "doi":
            return name

    raise ValueError(
        "DOI column not found. Use --doi-column to select one. "
        "Available columns: {}".format(", ".join(names))
    )


def read_dois_from_csv(
    csv_path: os.PathLike,
    doi_column: Optional[str] = None,
    encoding: str = "utf-8-sig",
) -> List[str]:
    with open(csv_path, mode="r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV file has no header row")

        column = _match_column(reader.fieldnames, doi_column)
        seen = set()
        dois = []
        for row in reader:
            doi = normalize_doi(row.get(column))
            if not doi or doi in seen:
                continue
            seen.add(doi)
            dois.append(doi)
        return dois


async def _download_infos(sh, infos, output: str, proxy: Optional[str]) -> None:
    loop = asyncio.get_running_loop()
    await sh.async_download(loop, infos, output, proxy=proxy)


def download_dois(
    dois: Iterable[str],
    output: str,
    proxy: Optional[str] = None,
    cookie: Optional[str] = None,
    cookie_file: Optional[os.PathLike] = None,
    dynamic_cookie: bool = False,
) -> int:
    from scihub_cn.scihub import SciHub

    proxy = normalize_proxy(proxy)
    os.makedirs(output, exist_ok=True)
    sh = SciHub(proxy=proxy, dynamic_cookie=dynamic_cookie)
    if cookie:
        sh.sess.headers.update({"Cookie": cookie})
        logger.info("Using Sci-Hub Cookie header with %d characters.", len(cookie))
    else:
        sh.mirror_cookies = load_mirror_cookies(cookie_file)
        logger.info("Using built-in Sci-Hub cookies for %s.", ", ".join(sorted(sh.mirror_cookies)))
    infos = []

    for doi in dois:
        try:
            logger.info("Resolving DOI: %s", doi)
            info = sh._get_paper_info(doi)
        except Exception as exc:
            logger.error("Failed to resolve DOI %s: %s", doi, exc)
            continue
        if info:
            infos.append(info)
        else:
            logger.error("No paper info found for DOI: %s", doi)

    if not infos:
        logger.warning("No downloadable paper info was resolved.")
        return 0

    asyncio.run(_download_infos(sh, infos, output, proxy))
    return len(infos)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read DOI values from a CSV file and download papers with scihub-cn."
    )
    parser.add_argument(
        "csv",
        nargs="?",
        default=r"D:\crawler2025\crawler_light\exports_812\sleep\cell\Cell\sleep_related_2020-01-01_2027-07-28.csv",
        help="CSV file containing DOI values",
    )
    parser.add_argument(
        "--doi-column",
        help="CSV column name containing DOI values. Defaults to a column named DOI.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="downloads",
        help="Directory to save downloaded PDFs. Defaults to current directory.",
    )
    parser.add_argument(
        "-p",
        "--proxy",
        default="http://127.0.0.1:7890",
        help="Proxy URL,s for example http://127.0.0.1:7890 or socks5h://127.0.0.1:10808.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="CSV file encoding. Defaults to utf-8-sig.",
    )
    parser.add_argument(
        "--cookie",
        default=os.environ.get("SCIHUB_COOKIE"),
        help="Override Cookie header for all mirrors. By default, built-in per-mirror cookies are used.",
    )
    parser.add_argument(
        "--cookie-file",
        type=Path,
        default=DEFAULT_COOKIE_FILE,
        help="JSON file with per-mirror cookies. Defaults to scihub_cookies.json next to this script.",
    )
    parser.add_argument(
        "--dynamic-cookie",
        action="store_true",
        help="Try a curl_cffi cf_clearance refresh when a mirror is blocked; static cookies remain the fallback.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print parsed DOI values; do not download.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args()

    dois = read_dois_from_csv(
        Path(args.csv), doi_column=args.doi_column, encoding=args.encoding
    )
    logger.info("Read %d unique DOI(s) from %s", len(dois), args.csv)

    if args.dry_run:
        for doi in dois:
            print(doi)
        return

    count = download_dois(
        dois,
        output=args.output,
        proxy=args.proxy,
        cookie=args.cookie,
        cookie_file=args.cookie_file,
        dynamic_cookie=args.dynamic_cookie,
    )
    logger.info("Submitted %d paper(s) for download.", count)


if __name__ == "__main__":
    main()
