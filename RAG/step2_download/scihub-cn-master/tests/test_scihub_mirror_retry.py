import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

import requests

sys.modules.setdefault("bibtexparser", types.ModuleType("bibtexparser"))

from scihub_cn import scihub as scihub_module
from scihub_cn.models import PaperDetailDescription
from scihub_cn.scihub import SciHub


class FakeCookies:
    def __init__(self, values):
        self.values = values

    def get_dict(self):
        return dict(self.values)


class FakeCurlResponse:
    def __init__(self, cookies):
        self.cookies = FakeCookies(cookies)


class FakeCurlSession:
    def __init__(self, responses, calls, **kwargs):
        self.responses = responses
        self.calls = calls
        self.kwargs = kwargs
        self.proxies = None
        self.trust_env = True

    def get(self, url, timeout):
        self.calls.append((self, url, timeout))
        return self.responses.pop(0)


def test_available_scihub_urls_use_only_configured_mirrors():
    sh = SciHub.__new__(SciHub)
    sh.proxies = None
    sh.sess = Mock()
    sh.sess.request.return_value = SimpleNamespace(
        content=(
            b'<html><body>'
            b'<a href="https://sci-hub.se">se duplicate</a>'
            b'<a href="https://sci-hub.wf">extra mirror</a>'
            b'</body></html>'
        )
    )

    urls = sh._get_available_scihub_urls()

    assert urls == [
        "https://sci-hub.box",
        "https://sci-hub.st",
        "https://sci-hub.su",
        "https://sci-hub.red",
        "https://sci-hub.ru",
        "https://sci-net.xyz",
    ]


def test_scihub_mirror_cookie_falls_back_to_sci_net_cookie():
    sh = SciHub.__new__(SciHub)
    sh.mirror_cookies = {
        "sci-net.xyz": "_ddg1=shared; connect.sid=session",
    }

    assert sh._get_cookie_for_url("https://sci-hub.box/10.1000/example") == "_ddg1=shared; connect.sid=session"
    assert sh._get_cookie_for_url("https://sci-net.xyz/storage/file.pdf") == "_ddg1=shared; connect.sid=session"


def test_scihub_init_logs_runtime_module_path_once(caplog):
    SciHub._runtime_logged = False

    SciHub()

    assert "Sci-Hub runtime module:" in caplog.text
    assert "scihub.py" in caplog.text


def test_native_cli_accepts_dynamic_cookie_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["scihub-cn", "--dynamic-cookie"])

    setting = scihub_module.construct_download_setting()

    assert setting.dynamic_cookie is True


def test_dynamic_cookie_accepts_cf_clearance_and_caches_session_by_host(monkeypatch):
    sh = SciHub.__new__(SciHub)
    sh.proxies = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
    sh.mirror_cookies = {"sci-hub.st": "static_cookie=ok"}
    sh._dynamic_cookie_sessions = {}
    calls = []
    responses = [FakeCurlResponse({"cf_clearance": "fresh", "session": "abc"})]

    def session_factory(**kwargs):
        return FakeCurlSession(responses, calls, **kwargs)

    monkeypatch.setattr(
        scihub_module,
        "curl_requests",
        SimpleNamespace(Session=session_factory),
        raising=False,
    )

    cookie = sh._get_fresh_cookie("https://sci-hub.st")

    assert cookie == "cf_clearance=fresh; session=abc"
    assert sh.mirror_cookies["sci-hub.st"] == cookie
    assert sh._dynamic_cookie_sessions["sci-hub.st"] is calls[0][0]
    assert calls[0][0].kwargs == {"impersonate": "chrome120", "verify": False}
    assert calls[0][0].proxies == sh.proxies
    assert calls[0][0].trust_env is False


def test_dynamic_cookie_failure_keeps_static_cookie(monkeypatch):
    sh = SciHub.__new__(SciHub)
    sh.proxies = None
    sh.mirror_cookies = {"sci-hub.st": "static_cookie=ok"}
    sh._dynamic_cookie_sessions = {}
    calls = []
    responses = [
        FakeCurlResponse({"session": "one"}),
        FakeCurlResponse({"session": "two"}),
        FakeCurlResponse({}),
    ]

    def session_factory(**kwargs):
        return FakeCurlSession(responses, calls, **kwargs)

    monkeypatch.setattr(
        scihub_module,
        "curl_requests",
        SimpleNamespace(Session=session_factory),
        raising=False,
    )

    assert sh._get_fresh_cookie("https://sci-hub.st") is None
    assert sh.mirror_cookies == {"sci-hub.st": "static_cookie=ok"}
    assert sh._dynamic_cookie_sessions == {}
    assert [call[0].kwargs["impersonate"] for call in calls] == [
        "chrome120",
        "chrome110",
        "safari15_5",
    ]


def test_search_paper_info_continues_after_mirror_request_error(monkeypatch):
    sh = SciHub.__new__(SciHub)
    sh.available_base_url_list = ["https://sci-hub.se", "https://sci-hub.st"]
    sh.base_url = "https://sci-hub.se/"
    sh.proxies = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
    sh.sess = Mock()
    sh.sess.request.side_effect = [
        requests.exceptions.SSLError("bad ssl"),
        SimpleNamespace(
            status_code=200,
            content=(
                b'<html><body><div id="citation">citation</div>'
                b'<iframe src="//download.example/paper.pdf"></iframe></body></html>'
            ),
        ),
    ]
    monkeypatch.setattr(
        scihub_module,
        "split_description",
        lambda _: PaperDetailDescription(
            authors="A. Author",
            title="Example Paper",
            publisher="Example Journal",
            doi="doi:10.1000/example",
        ),
    )
    monkeypatch.setattr(sh, "_is_pdf_available", lambda _: True)

    info = sh._search_paper_info("10.1000/example")

    assert info.url == "https://download.example/paper.pdf"
    assert sh.base_url == "https://sci-hub.st/"
    assert sh.sess.request.call_count == 2
    assert sh.sess.request.call_args_list[0].kwargs["timeout"] == 20


def test_search_paper_info_continues_after_mirror_without_pdf(monkeypatch):
    sh = SciHub.__new__(SciHub)
    sh.available_base_url_list = ["https://sci-hub.st", "https://sci-hub.ru"]
    sh.base_url = "https://sci-hub.st/"
    sh.proxies = None
    sh.sess = Mock()
    sh.sess.request.side_effect = [
        SimpleNamespace(status_code=200, content=b"<html><body>no pdf here</body></html>"),
        SimpleNamespace(
            status_code=200,
            content=(
                b'<html><body><div id="citation">citation</div>'
                b'<iframe src="//download.example/paper.pdf"></iframe></body></html>'
            ),
        ),
    ]
    monkeypatch.setattr(
        scihub_module,
        "split_description",
        lambda _: PaperDetailDescription(
            authors="A. Author",
            title="Example Paper",
            publisher="Example Journal",
            doi="doi:10.1000/example",
        ),
    )
    monkeypatch.setattr(sh, "_is_pdf_available", lambda _: True)

    info = sh._search_paper_info("10.1000/example")

    assert info.url == "https://download.example/paper.pdf"
    assert sh.base_url == "https://sci-hub.ru/"
    assert sh.sess.request.call_count == 2


def test_search_paper_info_retries_blocked_mirror_with_dynamic_cookie_session(monkeypatch):
    sh = SciHub.__new__(SciHub)
    sh.available_base_url_list = ["https://sci-hub.st"]
    sh.base_url = "https://sci-hub.st/"
    sh.proxies = None
    sh.dynamic_cookie = True
    sh._dynamic_cookie_attempted = set()
    sh._dynamic_cookie_sessions = {}
    sh.mirror_cookies = {"sci-hub.st": "static_cookie=ok"}
    sh.sess = Mock()
    sh.sess.headers = {"User-Agent": "UA"}
    sh.sess.request.return_value = SimpleNamespace(
        status_code=200,
        headers={"Content-Type": "text/html"},
        url="https://sci-hub.st/10.1000/example",
        history=[],
        content=b"<html><body>no pdf here</body></html>",
    )

    dynamic_session = Mock()
    dynamic_session.request.side_effect = [
        SimpleNamespace(
            status_code=200,
            headers={"Content-Type": "text/html"},
            url="https://sci-hub.st/10.1000/example",
            history=[],
            content=(
                b'<html><head><meta name="citation_title" content="Example Paper">'
                b'<meta name="citation_doi" content="10.1000/example">'
                b'<meta name="citation_pdf_url" content="/downloads/paper.pdf">'
                b'</head></html>'
            ),
        ),
        SimpleNamespace(
            status_code=200,
            headers={"Content-Type": "application/pdf"},
            url="https://sci-hub.st/downloads/paper.pdf",
            history=[],
            iter_content=lambda chunk_size: iter([b"%PDF-"]),
            close=lambda: None,
        ),
    ]

    def get_fresh_cookie(mirror_url):
        sh._dynamic_cookie_sessions["sci-hub.st"] = dynamic_session
        sh.mirror_cookies["sci-hub.st"] = "cf_clearance=fresh"
        return "cf_clearance=fresh"

    monkeypatch.setattr(sh, "_get_fresh_cookie", get_fresh_cookie)

    info = sh._search_paper_info("10.1000/example")

    assert info.url == "https://sci-hub.st/downloads/paper.pdf"
    assert sh._dynamic_cookie_attempted == {"sci-hub.st"}
    assert sh.sess.request.call_count == 1
    assert dynamic_session.request.call_count == 2


def test_search_paper_info_reads_object_pdf_and_citation_meta(monkeypatch):
    sh = SciHub.__new__(SciHub)
    sh.available_base_url_list = ["https://sci-hub.st"]
    sh.base_url = "https://sci-hub.st/"
    sh.proxies = None
    sh.sess = Mock()
    sh.sess.request.return_value = SimpleNamespace(
        status_code=200,
        content=(
            b'<html><head>'
            b'<meta name="citation_title" content="Sleep Loss Can Cause Death">'
            b'<meta name="citation_doi" content="10.1016/j.cell.2020.04.049">'
            b'<meta name="citation_journal_title" content="Cell">'
            b'<meta name="citation_author" content="Vaccaro, Alexandra">'
            b'<meta name="citation_pdf_url" content="/storage/paper.pdf">'
            b'</head><body>'
            b'<object data="/storage/paper.pdf#navpanes=0&view=FitH"></object>'
            b'</body></html>'
        ),
    )
    monkeypatch.setattr(sh, "_is_pdf_available", lambda _: True)

    info = sh._search_paper_info("10.1016/j.cell.2020.04.049")

    assert info.url == "https://sci-hub.st/storage/paper.pdf"
    assert info.title == "Sleep Loss Can Cause Death"
    assert info.doi == "10.1016/j.cell.2020.04.049"
    assert info.publisher == "Cell"
    assert info.authors == "Vaccaro, Alexandra"


def test_find_downloadable_pdf_uses_origin_mirror_cookie_for_same_host_relative_pdf():
    sh = SciHub.__new__(SciHub)
    sh.proxies = None
    sh.sess = Mock()
    sh.mirror_cookies = {
        "sci-hub.st": "mirror_cookie=ok",
    }
    sh.sess.headers = {"User-Agent": "UA"}
    sh.sess.request.return_value = SimpleNamespace(
        status_code=200,
        headers={"Content-Type": "application/pdf"},
        url="https://sci-hub.st/downloads/paper.pdf",
        history=[],
        iter_content=lambda chunk_size: iter([b"%PDF-"]),
        close=lambda: None,
    )

    pdf_url = sh._find_downloadable_pdf_url(
        "https://sci-hub.st",
        "/downloads/paper.pdf#view=FitH",
    )

    assert pdf_url == "https://sci-hub.st/downloads/paper.pdf"
    assert sh.sess.request.call_args.kwargs["headers"]["Cookie"] == "mirror_cookie=ok"


def test_dynamic_pdf_probe_error_is_treated_as_unavailable():
    sh = SciHub.__new__(SciHub)
    sh.proxies = None
    sh.sess = Mock()
    sh.sess.headers = {"User-Agent": "UA"}
    dynamic_session = Mock()
    dynamic_session.request.side_effect = RuntimeError("curl failed")
    sh._dynamic_cookie_sessions = {"sci-hub.st": dynamic_session}
    sh.mirror_cookies = {"sci-hub.st": "cf_clearance=fresh"}

    assert sh._is_pdf_available("https://sci-hub.st/downloads/paper.pdf") is False


def test_pdf_request_diagnostics_report_cookie_redirect_and_final_host():
    sh = SciHub.__new__(SciHub)
    sh.proxies = None
    sh.sess = Mock()
    sh.mirror_cookies = {"sci-hub.st": "mirror_cookie=ok"}
    sh.sess.headers = {"User-Agent": "UA"}
    sh.sess.request.return_value = SimpleNamespace(
        status_code=403,
        headers={"Content-Type": "text/html"},
        url="https://challenge.example/blocked",
        history=[
            SimpleNamespace(
                status_code=302,
                headers={"Location": "https://challenge.example/blocked"},
                url="https://sci-hub.st/downloads/paper.pdf",
            )
        ],
        content=b"forbidden",
    )

    response, diagnostics = sh.request_pdf_with_diagnostics(
        "https://sci-hub.st/downloads/paper.pdf",
        timeout=30,
    )

    assert response.status_code == 403
    assert diagnostics["cookie_sent"] is True
    assert diagnostics["cookie_host"] == "sci-hub.st"
    assert diagnostics["redirected"] is True
    assert diagnostics["redirect_chain"] == [
        "302:https://sci-hub.st/downloads/paper.pdf -> https://challenge.example/blocked"
    ]
    assert diagnostics["request_host"] == "sci-hub.st"
    assert diagnostics["final_host"] == "challenge.example"
    assert diagnostics["final_host_is_origin"] is False
    assert urlparse(diagnostics["final_url"]).hostname == "challenge.example"


def test_search_paper_info_logs_detail_page_diagnostics_on_403(caplog):
    sh = SciHub.__new__(SciHub)
    sh.available_base_url_list = ["https://sci-hub.st"]
    sh.base_url = "https://sci-hub.st/"
    sh.proxies = None
    sh.sess = Mock()
    sh.mirror_cookies = {"sci-hub.st": "mirror_cookie=ok"}
    sh.sess.headers = {"User-Agent": "UA"}
    sh.sess.request.return_value = SimpleNamespace(
        status_code=403,
        headers={"Content-Type": "text/html"},
        url="https://challenge.example/blocked",
        history=[
            SimpleNamespace(
                status_code=302,
                headers={"Location": "https://challenge.example/blocked"},
                url="https://sci-hub.st/10.1000/example",
            )
        ],
        content=b"forbidden",
    )

    try:
        sh._search_paper_info("10.1000/example")
    except Exception:
        pass

    log_text = caplog.text
    assert "returned status 403" in log_text
    assert "cookie_sent=True" in log_text
    assert "redirected=True" in log_text
    assert "request_host=sci-hub.st" in log_text
    assert "final_host=challenge.example" in log_text
    assert "final_host_is_origin=False" in log_text
