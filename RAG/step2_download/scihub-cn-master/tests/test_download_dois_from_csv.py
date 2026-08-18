import pytest

import download_dois_from_csv
from download_dois_from_csv import (
    DEFAULT_SCIHUB_COOKIE,
    DEFAULT_MIRROR_COOKIES,
    build_parser,
    download_dois,
    read_dois_from_csv,
)


def test_read_dois_from_csv_auto_detects_doi_column_and_deduplicates(tmp_path):
    csv_path = tmp_path / "papers.csv"
    csv_path.write_text(
        "Title, DOI ,Note\n"
        "Paper A, 10.1000/abc ,first\n"
        "Paper B,,missing\n"
        "Paper C,10.1000/abc,duplicate\n"
        "Paper D,https://doi.org/10.2000/xyz,doi url\n",
        encoding="utf-8",
    )

    assert read_dois_from_csv(csv_path) == ["10.1000/abc", "10.2000/xyz"]


def test_read_dois_from_csv_uses_explicit_column(tmp_path):
    csv_path = tmp_path / "papers.csv"
    csv_path.write_text("article_doi\n10.3000/demo\n", encoding="utf-8")

    assert read_dois_from_csv(csv_path, doi_column="article_doi") == ["10.3000/demo"]


def test_read_dois_from_csv_reports_missing_doi_column(tmp_path):
    csv_path = tmp_path / "papers.csv"
    csv_path.write_text("title,url\nPaper,https://example.com\n", encoding="utf-8")

    with pytest.raises(ValueError, match="DOI column"):
        read_dois_from_csv(csv_path)


def test_parser_allows_default_csv_when_no_argument_is_provided():
    args = build_parser().parse_args([])

    assert args.csv


def test_parser_uses_default_proxy_when_no_argument_is_provided():
    args = build_parser().parse_args([])

    assert args.proxy == "http://127.0.0.1:7890"


def test_parser_accepts_cookie_argument():
    args = build_parser().parse_args(["--cookie", "foo=bar"])

    assert args.cookie == "foo=bar"


def test_parser_accepts_dynamic_cookie_flag():
    args = build_parser().parse_args(["--dynamic-cookie"])

    assert args.dynamic_cookie is True


def test_parser_uses_default_cookie_when_no_argument_is_provided(monkeypatch):
    monkeypatch.delenv("SCIHUB_COOKIE", raising=False)

    args = build_parser().parse_args([])

    assert args.cookie is None


def test_download_dois_adds_cookie_to_scihub_session(monkeypatch, tmp_path):
    created = {}

    class FakeSession:
        def __init__(self):
            self.headers = {}

    class FakeSciHub:
        def __init__(self, proxy=None, dynamic_cookie=False):
            self.sess = FakeSession()
            created["instance"] = self

        def _get_paper_info(self, doi):
            return None

    monkeypatch.setattr(
        "scihub_cn.scihub.SciHub",
        FakeSciHub,
    )

    download_dois(["10.1000/example"], str(tmp_path), cookie="foo=bar")

    assert created["instance"].sess.headers["Cookie"] == "foo=bar"


def test_download_dois_normalizes_proxy_before_creating_scihub(monkeypatch, tmp_path):
    created = {}

    class FakeSession:
        def __init__(self):
            self.headers = {}

    class FakeSciHub:
        def __init__(self, proxy=None, dynamic_cookie=False):
            self.sess = FakeSession()
            self.proxy = proxy
            created["instance"] = self

        def _get_paper_info(self, doi):
            return None

    monkeypatch.setattr("scihub_cn.scihub.SciHub", FakeSciHub)

    download_dois(["10.1000/example"], str(tmp_path), proxy="socks5://127.0.0.1:10808")

    assert created["instance"].proxy == "socks5h://127.0.0.1:10808"


def test_download_dois_enables_dynamic_cookie_on_scihub(monkeypatch, tmp_path):
    created = {}

    class FakeSession:
        def __init__(self):
            self.headers = {}

    class FakeSciHub:
        def __init__(self, proxy=None, dynamic_cookie=False):
            self.sess = FakeSession()
            self.dynamic_cookie = dynamic_cookie
            created["instance"] = self

        def _get_paper_info(self, doi):
            return None

    monkeypatch.setattr("scihub_cn.scihub.SciHub", FakeSciHub)

    download_dois(
        ["10.1000/example"],
        str(tmp_path),
        dynamic_cookie=True,
    )

    assert created["instance"].dynamic_cookie is True


def test_download_dois_uses_builtin_mirror_cookies_without_override(monkeypatch, tmp_path):
    created = {}

    class FakeSession:
        def __init__(self):
            self.headers = {}

    class FakeSciHub:
        def __init__(self, proxy=None, dynamic_cookie=False):
            self.sess = FakeSession()
            created["instance"] = self

        def _get_paper_info(self, doi):
            return None

    monkeypatch.setattr("scihub_cn.scihub.SciHub", FakeSciHub)

    download_dois(
        ["10.1000/example"],
        str(tmp_path),
        cookie_file=tmp_path / "missing-cookies.json",
    )

    assert created["instance"].mirror_cookies == DEFAULT_MIRROR_COOKIES


def test_builtin_mirror_cookies_include_sci_net_fallback():
    assert "sci-net.xyz" in DEFAULT_MIRROR_COOKIES
    assert "connect.sid=" in DEFAULT_MIRROR_COOKIES["sci-net.xyz"]
