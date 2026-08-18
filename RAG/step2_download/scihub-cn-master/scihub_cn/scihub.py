# -*- coding: utf-8 -*-

"""
Sci-API Unofficial API
[Search|Download] research papers from [scholar.google.com|sci-hub.io].

@author zaytoun hulei6188
@updated by Python实用宝典
"""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
from typing import Dict, Union, Tuple, Optional
from urllib.parse import urlparse, urljoin

import aiohttp
import requests
import urllib3
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

from scihub_cn.exceptions import ArgumentsError, VerificationError, ScholarConf
from scihub_cn.models import SearchEngine, DownLoadSetting, DownLoadCommandSetting, DownLoadCommandFileSetting, \
    PaperInfo, PaperDetailDescription
# log config
from scihub_cn.utils import translate, split_description

logging.basicConfig()
logger = logging.getLogger('Sci-Hub')
logger.setLevel(logging.INFO)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# constants
SCHOLARS_BASE_URL = 'https://www.sciencedirect.com/search/api'
GOOGLE_SCHOLAR_URL = 'https://scholar.google.com/scholar'
WEB_OF_SCIENCE_URL = 'https://publons.com/publon/list/'
BAIDU_XUESHU_URL = 'https://xueshu.baidu.com/s'
SCI_HUB_MIRRORS = [
    "https://sci-hub.box",
    "https://sci-hub.st",
    "https://sci-hub.su",
    "https://sci-hub.red",
    "https://sci-hub.ru",
    "https://sci-net.xyz",
]
SCI_HUB_STORAGE_MIRRORS = [
    "https://sci-net.xyz",
]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',
}


def filter_none(arr):
    """除去数组的空值"""
    return list(filter(lambda _: _, arr))


def construct_download_setting():
    parser = argparse.ArgumentParser(
        prog="scihub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='''
           SciHub to PDF
           ----------------------------------------------------
           使用doi，论文标题，或者bibtex文件批量下载论文

           给出bibtex文件

           $ scihub-cn -i mybibtex.bib --bib

           给出论文doi名称

           $ scihub-cn -d 10.1038/s41524-017-0032-0

           给出论文url

           $ scihub-cn -u https://ieeexplore.ieee.org/document/9429985

           给出论文关键字(关键字之间用_链接,如machine_learning)

           $ scihub-cn -w word1_words2_words3


           给出论文doi的txt文本文件，比如

           ```
           10.1038/s41524-017-0032-0
           10.1063/1.3149495
           ```
           $ scihub-cn -i dois.txt --doi
           给出所有论文名称的txt文本文件

           ```
           Some Title 1
           Some Title 2
           ```
           $ scihub-cn -i titles.txt --title
           给出所有论文url的txt文件
           ```
           url 1
           url 2
           ```
           $ scihub-cn -i urls.txt --url

           你可以在末尾添加-p(--proxy),-o(--output),-e(--engine)，-l(--limit)来指定代理，输出文件夹、搜索引擎以及限制的搜索的条目数
           搜索引擎包括 google_scholar、baidu_xueshu、publons、以及science_direct
           ''')
    parser.add_argument("-u", dest="url", help="input the download url")
    parser.add_argument("-d", dest="doi", help="input the download doi")
    parser.add_argument(
        "--input", "-i",
        dest="inputfile",
        help="input download file",
    )

    parser.add_argument(
        "-w", "--words",
        dest="words",
        help="download from some key words,keywords are linked by _,like machine_learning."
    )
    parser.add_argument("--title",
                        dest="title_file",
                        action="store_true",
                        help="download from paper titles file")
    parser.add_argument(
        "-p", "--proxy",
        dest="proxy",
        help="use proxy to download papers",
    )
    parser.add_argument(
        "--output", "-o",
        dest="output",
        help="setting output path",
    )
    parser.add_argument(
        "--doi",
        dest="doi_file",
        action="store_true",
        help="download paper from dois file",
    )
    parser.add_argument("--bib", action="store_true", dest="bibtex_file", help="download papers from bibtex file")
    parser.add_argument("--url", dest="url_file", action="store_true", help="download paper from url file")
    parser.add_argument("-e", "--engine", dest="search_engine", help="set the search engine")
    parser.add_argument("-l", "--limit", dest="limit", help="limit the number of search result")
    parser.add_argument(
        "--dynamic-cookie",
        action="store_true",
        help="refresh cf_clearance with curl_cffi when a mirror is blocked",
    )
    command_args = parser.parse_args()

    if command_args.inputfile:
        setting = DownLoadCommandFileSetting()  # 从命令行得到的文件路径中下载
        if command_args.url_file:
            setting.urls_file = command_args.inputfile
        if command_args.doi_file:
            setting.dois_file = command_args.inputfile
        if command_args.title_file:
            setting.title_file = command_args.inputfile
        if command_args.bibtex_file:
            setting.bibtex_file = command_args.inputfile
        if not setting.urls_file and not setting.dois_file and not setting.title_file and not setting.bibtex_file:
            raise ArgumentsError("error:你没有给出输入文件的类型！")

    else:
        setting = DownLoadCommandSetting()
        if command_args.words:
            setting.words = command_args.words.split('_')
        if command_args.url:
            setting.url = command_args.url
        if command_args.doi:
            setting.doi = command_args.doi
        if not setting.words and not setting.url and not setting.doi:
            setting = DownLoadCommandFileSetting()

    # with open('./config.yml', mode='rt') as f:
    #     res = yaml.load(f, yaml.FullLoader)
    #     try:
    #         setting.search_engine = SearchEngine[res['search-engine']]
    #     except Exception as e:
    #         raise ArgumentsError(
    #             'search-engine must be selected from google_scholar, baidu_xueshu, publons and science_direct')
    #     if 'proxy' in res:
    #         setting.proxy = 'http://' + (res['proxy']['ip'] + ':' + str(res['proxy']['port']))
    #
    #     if 'output' in res:
    #         setting.outputPath = res['output']
    #     if 'limit' in res:
    #         setting.limit = res['limit']

    if command_args.proxy:
        proxy = command_args.proxy
        if not proxy:
            setting.proxy = None
        elif not proxy.lower().startswith((
            'http://', 'https://', 'socks4://', 'socks4a://', 'socks5://', 'socks5h://',
        )):
            setting.proxy = 'http://' + command_args.proxy
        else:
            setting.proxy = command_args.proxy

    if command_args.output:
        setting.outputPath = command_args.output
    setting.dynamic_cookie = command_args.dynamic_cookie
    if command_args.limit:
        setting.limit = int(command_args.limit)
    try:
        if command_args.search_engine:
            setting.search_engine = SearchEngine[command_args.search_engine]
    except Exception as e:
        raise ArgumentsError(
            'search-engine must be selected from GOOGLE_SCHOLAR or BAIDU_XUESHU or PUBLONS or SCIENCE_DIRECT')
    return setting


def readline_paper_info(file_name):
    res = None
    with open(file_name, mode='rt', encoding='utf8') as f:
        res = f.readlines()
    return [item if not item.endswith('\n') else item[:-1] for item in res]


class SciHub(object):
    """
    SciHub class can search for papers on Google Scholars
    and fetch/download papers from sci-hub.io
    """
    _runtime_logged = False

    def __init__(self, proxy=None, dynamic_cookie=False):
        if not SciHub._runtime_logged:
            logger.info('Sci-Hub runtime module: %s' % __file__)
            SciHub._runtime_logged = True
        self.sess = requests.Session()
        self.sess.trust_env = False
        self.sess.headers = HEADERS
        self.proxies = self.get_proxies(proxy)
        self.dynamic_cookie = bool(dynamic_cookie)
        self._dynamic_cookie_sessions = {}
        self._dynamic_cookie_attempted = set()
        self.available_base_url_list = self._get_available_scihub_urls()
        self.base_url = self.available_base_url_list[0] + '/'

    def search(self, search_engine, query, limit=10, cookie=''):
        """选择一个搜索引擎搜索内容"""
        if search_engine == SearchEngine.google_scholar:
            return self.search_by_google_scholar(query, limit)
        elif search_engine == SearchEngine.baidu_xueshu:
            return self.search_by_baidu(query, limit)
        elif search_engine == SearchEngine.science_direct:
            return self.search_by_science_direct(query, cookie, limit)
        else:
            return self.search_by_publons(query, limit)

    def _get_available_scihub_urls(self):
        '''
        Finds available scihub urls via http://tool.yovisun.com/scihub/
        '''
        return list(SCI_HUB_MIRRORS)

    def _get_cookie_for_url(self, url):
        mirror_cookies = getattr(self, 'mirror_cookies', None) or {}
        host = urlparse(url).hostname or ''
        cookie = mirror_cookies.get(host) or mirror_cookies.get(host.replace('www.', '', 1))
        if cookie:
            return cookie
        if host.startswith('sci-hub.'):
            return mirror_cookies.get('sci-net.xyz')
        return None

    def _get_fresh_cookie(self, mirror_url):
        """Get and cache a Cloudflare clearance cookie for one mirror host."""
        if curl_requests is None:
            logger.info('curl_cffi is unavailable; keeping the configured static Sci-Hub Cookie.')
            return None

        host = urlparse(mirror_url).hostname or ''
        if not host:
            return None

        for impersonate in ('chrome120', 'chrome110', 'safari15_5'):
            try:
                session = curl_requests.Session(impersonate=impersonate, verify=False)
                session.trust_env = False
                if self.proxies:
                    session.proxies = dict(self.proxies)
                response = session.get(mirror_url, timeout=30)
                cookies = response.cookies.get_dict()
                if 'cf_clearance' not in cookies:
                    logger.info(
                        'No cf_clearance received from %s with impersonate=%s; trying next fingerprint.',
                        host,
                        impersonate,
                    )
                    continue

                cookie = '; '.join('%s=%s' % item for item in cookies.items())
                mirror_cookies = getattr(self, 'mirror_cookies', None)
                if mirror_cookies is None:
                    mirror_cookies = {}
                    self.mirror_cookies = mirror_cookies
                mirror_cookies[host] = cookie
                self._dynamic_cookie_sessions[host] = session
                logger.info(
                    'Refreshed dynamic Sci-Hub Cookie for %s with impersonate=%s.',
                    host,
                    impersonate,
                )
                return cookie
            except Exception as exc:
                logger.info(
                    'Dynamic Sci-Hub Cookie request failed for %s with impersonate=%s: %s',
                    host,
                    impersonate,
                    exc,
                )

        logger.info('Dynamic Cookie refresh failed for %s; keeping the configured static Cookie.', host)
        return None

    def _get_headers_for_url(self, url):
        session_headers = getattr(self.sess, 'headers', None)
        headers = dict(session_headers) if isinstance(session_headers, dict) else dict(HEADERS)
        cookie = self._get_cookie_for_url(url)
        if cookie:
            headers['Cookie'] = cookie
        return headers

    def _activate_dynamic_cookie(self, mirror_url):
        if not getattr(self, 'dynamic_cookie', False):
            return False
        host = urlparse(mirror_url).hostname or ''
        attempted = getattr(self, '_dynamic_cookie_attempted', None)
        if attempted is None:
            attempted = set()
            self._dynamic_cookie_attempted = attempted
        if not host or host in attempted:
            return False
        attempted.add(host)
        return bool(self._get_fresh_cookie(mirror_url))

    def _absolute_url(self, base_url, url):
        return urljoin(base_url.rstrip('/') + '/', url)

    def _response_redirect_chain(self, response):
        chain = []
        for item in getattr(response, 'history', None) or []:
            location = getattr(item, 'headers', {}).get('Location', '')
            chain.append('%s:%s -> %s' % (getattr(item, 'status_code', ''), getattr(item, 'url', ''), location))
        return chain

    def describe_pdf_request(self, request_url, response, cookie_sent):
        request_host = urlparse(request_url).hostname or ''
        final_url = getattr(response, 'url', None) or request_url
        final_host = urlparse(final_url).hostname or ''
        return {
            'request_url': request_url,
            'request_host': request_host,
            'final_url': final_url,
            'final_host': final_host,
            'final_host_is_origin': final_host == request_host,
            'status_code': getattr(response, 'status_code', None),
            'content_type': getattr(response, 'headers', {}).get('Content-Type', ''),
            'cookie_sent': bool(cookie_sent),
            'cookie_host': request_host if cookie_sent else '',
            'redirected': bool(getattr(response, 'history', None)),
            'redirect_chain': self._response_redirect_chain(response),
        }

    def request_pdf_with_diagnostics(self, url, timeout=20, stream=False):
        return self.request_with_diagnostics(url, timeout=timeout, stream=stream)

    def request_with_diagnostics(self, url, timeout=20, stream=False):
        headers = self._get_headers_for_url(url)
        host = urlparse(url).hostname or ''
        dynamic_session = getattr(self, '_dynamic_cookie_sessions', {}).get(host)
        if dynamic_session is not None:
            response = dynamic_session.request(
                method='GET', url=url, timeout=timeout, headers=headers,
                stream=stream, allow_redirects=True,
            )
        else:
            response = self.sess.request(method='GET', url=url, verify=False, proxies=self.proxies,
                                         timeout=timeout, headers=headers, stream=stream, allow_redirects=True)
        return response, self.describe_pdf_request(url, response, bool(headers.get('Cookie')))

    def _is_pdf_available(self, url):
        try:
            res, diagnostics = self.request_pdf_with_diagnostics(url, timeout=20, stream=True)
            content_type = res.headers.get('Content-Type', '').lower()
            first_chunk = next(res.iter_content(chunk_size=5), b'')
            res.close()
            ok = res.status_code == 200 and ('application/pdf' in content_type or first_chunk.startswith(b'%PDF'))
            if not ok:
                logger.info('PDF probe failed: %s' % diagnostics)
            return ok
        except Exception as e:
            logger.info('Cannot verify PDF url %s: %s' % (url, e))
            return False

    def _find_downloadable_pdf_url(self, base_url, pdf_url):
        pdf_path = pdf_url.split('#', 1)[0]
        candidate_urls = [self._absolute_url(base_url, pdf_path)]
        if pdf_path.startswith('/'):
            for storage_base_url in SCI_HUB_STORAGE_MIRRORS:
                candidate = self._absolute_url(storage_base_url, pdf_path)
                if candidate not in candidate_urls:
                    candidate_urls.append(candidate)
        for candidate in candidate_urls:
            if self._is_pdf_available(candidate):
                return candidate
        return None

    def get_proxies(self, proxy):
        '''
        set proxy for session
        :param proxy_dict:
        :return:
        '''
        proxy = str(proxy or '').strip()
        if proxy.lower() in {'', '0', 'none', 'no', 'false', 'off', 'direct'}:
            return None
        if proxy.lower().startswith('socks5://'):
            proxy = 'socks5h://' + proxy[len('socks5://'):]
        elif not proxy.lower().startswith((
            'http://', 'https://', 'socks4://', 'socks4a://', 'socks5h://',
        )):
            proxy = 'http://' + proxy
        if proxy:
            return {
                "http": proxy,
                "https": proxy, }
        return None

    def _change_base_url(self):
        if not self.available_base_url_list:
            raise Exception('Ran out of valid sci-hub urls')
        del self.available_base_url_list[0]
        self.base_url = self.available_base_url_list[0] + '/'
        logger.info("I'm changing to {}".format(self.available_base_url_list[0]))

    def search_by_science_direct(self, query, cookie, limit=10):
        """
        通过science direct搜索，需要配置Cookie
        """
        start = 0
        results = []
        self.sess.headers["Cookie"] = cookie
        while True:
            try:
                res = self.sess.request(method='GET', url=SCHOLARS_BASE_URL,
                                        params={'qs': ' '.join(query), 'offset': start,
                                                "hostname": "www.sciencedirect.com"},
                                        proxies=self.proxies)
            except requests.exceptions.RequestException as e:
                logger.error('Failed to complete search with query %s (connection error)' % query)
                return results
            try:
                s = json.loads(res.content)
            except Exception as e:
                logger.exception(e)
                return results

            papers = s.get('searchResults')
            if not papers:
                return results

            for paper in papers:
                paper_info = self._get_paper_info(paper['doi'])
                if paper_info:
                    results.append(paper_info)
                    if len(results) >= limit:
                        return results

            start += 25

    def search_by_publons(self, query, limit=10):
        """
        使用publons进行文献搜索
        """
        start = 0
        results = []
        while True:
            try:
                res = self.sess.request(method='GET', url=WEB_OF_SCIENCE_URL,
                                        params={'title': ' '.join(query), 'page': start}, proxies=self.proxies)
            except requests.exceptions.RequestException as e:
                logger.error('Failed to complete search with query %s (connection error)' % query)
                return results

            papers = json.loads(res.content).get("results", [])

            for paper in papers:
                paper_info = self._get_paper_info(paper['doi'])
                if paper_info:
                    results.append(paper_info)
                    if len(results) >= limit:
                        return results

            start += 1

    def search_by_baidu(self, query, limit=10):
        """
        默认使用百度学术进行文献搜索
        """

        def fetch_doi(url):
            res = self.sess.request(method='GET', url=url, proxies=self.proxies)
            s = self._get_soup(res.content)
            dois = [doi.text.replace("DOI：", "").replace("ISBN：", "").strip() for doi in
                    s.find_all('div', class_='doi_wr')]
            if dois:
                return dois[0]
            else:
                return ""

        start = 0

        results = []
        while True:
            try:
                res = self.sess.request(method='GET', url=BAIDU_XUESHU_URL,
                                        params={'wd': ' '.join(query), 'pn': start, 'filter': 'sc_type%3D%7B1%7D'},
                                        proxies=self.proxies)
            except requests.exceptions.RequestException as e:
                logger.error('Failed to complete search with query %s (connection error)' % query)
                return results

            s = self._get_soup(res.content)
            papers = s.find_all('div', class_="result")

            for paper in papers:
                if not paper.find('table'):
                    link = paper.find('h3', class_='t c_font')
                    url = str(link.find('a')['href'].replace("\n", "").strip())
                    paper_info = self._get_paper_info(fetch_doi(url))
                    if paper_info:
                        results.append(paper_info)
                        if len(results) >= limit:
                            return results

            start += 10

    def download(self, info: Dict, destination='', is_translate_title=False) -> Optional[PaperInfo]:
        """
        Downloads a paper from sci-hub given an indentifier (DOI, PMID, URL).
        Currently, this can potentially be blocked by a captcha if a certain
        limit has been reached.
        :param info: {"doi": '10.1109/ACC.1999.dddddd'}
            optional: doi
            optional: title -> deprecated
            optional: scihub_url
        :param destination: save path, default current work directory
        :param is_translate_title: translate paper's title as the saved file's filename?
        """
        if 'response' in info:  # 给出的info本身就是一个下载链接时, {"response": "https://.../downloads/..."}
            res = info['response']
            save_name = self._generate_name_hash(info['response'])
        else:
            # res is the resource of file
            res, paper_info = self.fetch(info)
            save_name = translate(paper_info.title, proxy=self.proxies) if is_translate_title else paper_info.title

        if type(res) == dict and 'err' in res:
            logger.error(res['err'])
            return None
        if not res:
            return None
        self._save(res.content,
                   os.path.join(destination, self._vaild_name(save_name)))
        return paper_info

    def fetch(self, info) -> Tuple[Union[requests.Response, Dict], Optional[PaperInfo]]:
        """
        Fetches the paper by first retrieving the direct link to the pdf.
        If the indentifier is a DOI, PMID, or URL pay-wall, then use Sci-Hub
        to access and download paper. Otherwise, just download paper directly.
        """
        url = ""
        try:
            if 'doi' in info and info['doi']:
                paper_info: PaperInfo = self._get_paper_info(info['doi'])
            # 从scihub网站上有时爬不到论文doi的信息 如文章10.1609/aimag.v18i4.1324
            else:
                pattern = re.compile('https?://sci-hub.*?/')
                # 根据提供的url来截取获得其 identifier
                paper_info: PaperInfo = self._get_paper_info(
                    info['scihub_url'][pattern.search(info['scihub_url']).end():]
                )
            # verify=False is dangerous but sci-hub.io requires intermediate certificates to verify
            # and requests doesn't know how to download them. as a hacky fix, you can add them to your store
            # and verifying would work. will fix this later.
            res = self.sess.request(method='GET', url=self.base_url + paper_info.url if not paper_info.url.startswith(
                "http") else paper_info.url, verify=True, proxies=self.proxies)

            if res.headers['Content-Type'] != 'application/pdf':
                self._change_base_url()
                logger.info('由于验证码问题，获取 pdf 失败 论文名称: %s '
                            '(resolved url %s)' % (info['title'], paper_info.url))
            else:
                return res, paper_info
        except requests.exceptions.ConnectionError:
            logger.info('Cannot access {}, changing url'.format(self.available_base_url_list[0]))
            self._change_base_url()

        except requests.exceptions.RequestException as e:
            logger.info('由于请求失败，获取pdf失败 论文名称: %s (resolved url %s).'
                        % (info['title'], url))
            return {
                       'err': '由于请求失败，获取pdf失败 论文名称:%s (resolved url %s).'
                              % (info['title'], url)
                   }, None

    def _get_paper_info(self, identifier: str) -> Optional[PaperInfo]:
        f"""
        Finds the paper info includes {PaperInfo}'s info for a given identifier.
        :param identifier: [doi detail, scihub_url detail]
        """
        id_type = self._classify(identifier)
        # id_type == 'url-direct', identifier is a url and endswith `pdf`
        return PaperInfo(url=identifier, title=hashlib.md5(identifier).hexdigest(),
                         doi="None") if id_type == 'url-direct' \
            else self._search_paper_info(identifier)

    def _search_paper_info(self, identifier: str) -> Optional[PaperInfo]:
        """
        Sci-Hub embeds papers in an iframe. This function finds the actual
        source url which looks something like https://moscow.sci-hub.io/.../....pdf.
        """
        
        last_error = None
        for available_base_url in self.available_base_url_list:
            pdf_url = None
            s = None
            request_url = available_base_url + '/' + identifier
            while True:
                try:
                    res, diagnostics = self.request_with_diagnostics(request_url, timeout=20)
                except Exception as e:
                    last_error = e
                    logger.info('Cannot access %s, trying next Sci-Hub url: %s' % (available_base_url, e))
                    break

                content = getattr(res, 'content', b'') or b''
                challenge_page = any(marker in content.lower() for marker in (
                    b'cloudflare', b'attention required', b'turnstile',
                ))
                if res.status_code != 200:
                    if (
                        res.status_code in (403, 429, 503) or challenge_page
                    ) and self._activate_dynamic_cookie(available_base_url):
                        logger.info('Retrying %s with a refreshed dynamic Cookie.', available_base_url)
                        continue
                    logger.info(
                        'Sci-Hub url %s returned status %s, trying next url '
                        '(cookie_sent=%s; redirected=%s; request_host=%s; final_host=%s; '
                        'final_host_is_origin=%s; final_url=%s; redirect_chain=%s)' %
                        (
                            available_base_url,
                            res.status_code,
                            diagnostics['cookie_sent'],
                            diagnostics['redirected'],
                            diagnostics['request_host'],
                            diagnostics['final_host'],
                            diagnostics['final_host_is_origin'],
                            diagnostics['final_url'],
                            diagnostics['redirect_chain'],
                        )
                    )
                    break

                self.base_url = available_base_url + '/'
                logger.info("Fetching %s ...", self.base_url + identifier)
                s = self._get_soup(content)
                frame = s.find('iframe') or s.find('embed') or s.find('object')
                if frame:
                    pdf_url = frame.get('src') or frame.get('data')
                if not pdf_url:
                    pdf_meta = s.find('meta', attrs={'name': 'citation_pdf_url'})
                    pdf_url = pdf_meta.get('content') if pdf_meta else None
                if not pdf_url:
                    if self._activate_dynamic_cookie(available_base_url):
                        logger.info('Retrying %s with a refreshed dynamic Cookie.', available_base_url)
                        continue
                    page_title = s.find('title')
                    if page_title and ('robot' in page_title.text.lower() or '\u0440\u043e\u0431\u043e\u0442' in page_title.text.lower()):
                        logger.info('Sci-Hub url %s returned a robot verification page; pass a valid browser Cookie.' %
                                    available_base_url)
                    logger.info('Sci-Hub url %s has no downloadable PDF frame, trying next url' % available_base_url)
                    break
                pdf_url = self._find_downloadable_pdf_url(available_base_url, pdf_url)
                if not pdf_url:
                    logger.info('Sci-Hub url %s found a PDF link but it is not downloadable, trying next url' %
                                available_base_url)
                break

            if not pdf_url or s is None:
                continue

            citation = s.find("div", id="citation")
            paperDetailDescription = split_description(citation.text.strip()) if citation else None
            if paperDetailDescription:
                title = paperDetailDescription.title
                doi = paperDetailDescription.doi
                publisher = paperDetailDescription.publisher
                authors = paperDetailDescription.authors
            else:
                def meta_content(name):
                    tag = s.find('meta', attrs={'name': name})
                    return tag.get('content', '').strip() if tag else ''

                title = meta_content('citation_title')
                doi = meta_content('citation_doi')
                publisher = meta_content('citation_journal_title')
                authors = '; '.join(
                    tag.get('content', '').strip()
                    for tag in s.find_all('meta', attrs={'name': 'citation_author'})
                    if tag.get('content', '').strip()
                )
                if not title:
                    page_title = s.find('title')
                    title = page_title.text.strip() if page_title else ''
                    title = re.sub(r'^Sci-\w+:\s*', '', title)
            if not title:
                logger.info('Sci-Hub url %s has no paper title, trying next url' % available_base_url)
                continue
            return PaperInfo(
                url=pdf_url,
                title=title,
                doi=doi,
                publisher=publisher,
                authors=authors
            )
        else:
            if last_error:
                logger.error('Last Sci-Hub connection error: %s' % last_error)
            raise Exception('No configured Sci-Hub mirror returned a downloadable PDF.')
            raise Exception('http://tool.yovisun.com/scihub/中各个链接均无法在程序中正常运行，下载失败！')
            
        logger.info(f"获取 {self.base_url + identifier} 中...")
    def _classify(self, identifier):
        """
        Classify the type of identifier:
        url-direct - openly accessible paper
        url-non-direct - pay-walled paper
        pmid - PubMed ID
        doi - digital object identifier
        """
        if (identifier.startswith('http') or identifier.startswith('https')):
            if identifier.endswith('pdf'):
                return 'url-direct'
            else:
                return 'url-non-direct'
        elif identifier.isdigit():
            return 'pmid'
        else:
            return 'doi'

    def _save(self, data, path):
        """
        Save a file give data and a path.
        """
        with open(path, 'wb') as f:
            f.write(data)

    def _get_soup(self, html):
        """
        Return html soup.
        """
        return BeautifulSoup(html, 'html.parser')

    def generate_paper_info(self, identifier):
        """
        根据标识符获得论文的有效信息标识符可以是url或者doi

        """
        if identifier.startswith('http://') or identifier.startswith('https://'):
            check_info = self.check_download_url(identifier)
            if check_info:
                return check_info
        res = self.sess.request(method='GET', url=self.base_url + identifier, verify=False,
                                headers={'User-Agent': ScholarConf.USER_AGENT}, proxies=self.proxies)
        if len(res.content) <= 0:
            return None

        s = self._get_soup(res.content)
        try:
            scihub_url = 'https:' + s.find('div', attrs={'id': 'link'}).find('a').attrs['href']
            citation = s.find(name='div', attrs={'id': 'citation'}, recursive=True)
            title = citation.find('i')
            doi_location = citation.text.find('doi:')
            name = title.text if title else citation.text[:doi_location]
            doi = citation.text[doi_location + 4:-1]
            frame = s.find('iframe') or s.find('embed')
            download_url = None
            if frame:
                download_url = frame.get('src') if not frame.get('src').startswith('//') \
                    else 'http:' + frame.get('src')
        except Exception as e:
            logger.info(identifier + f'  scihub数据库不存在这篇论文：{e}')
            return None
        return {'title': name, 'doi': doi, 'scihub_url': scihub_url, 'download_url': download_url}

    def generate_paper_info_by_bibtex(self, bibtex_file_path):
        """
        从bibtex文件中获得论文信息
        Returns:

        """
        import bibtexparser

        with open(bibtex_file_path) as bibtex_file:
            bib_database = bibtexparser.load(bibtex_file)

        res = []
        for info in bib_database.entries:
            if 'title' in info and 'url' in info and 'doi' in info:
                res.append(info)
            else:
                paper_info = None
                if 'doi' in info and not paper_info:
                    paper_info = self._get_paper_info(info['doi'])
                if 'url' in info and not paper_info:
                    paper_info = self._get_paper_info(info['url'])
                if not paper_info:
                    res.append(paper_info)
                else:
                    logger.info(info + '该文章信息不全面，无法下载！')
        return res

    def _generate_name_hash(self, res):
        """
        Generate unique filename for paper. Returns a name by calcuating
        md5 hash of file contents, then appending the last 20 characters
        of the url which typically provides a good paper identifier.
        """
        name = res.url.split('/')[-1]
        name = re.sub('#view=(.+)', '', name)
        pdf_hash = hashlib.md5(res.content).hexdigest()
        return '%s-%s' % (pdf_hash, name[-20:])

    def _vaild_name(self, name):
        """
        使得下载的论文名称合法
        """
        if name.endswith('.pdf'):
            name = name[:name.rfind('.pdf')]
        max_len = 223
        name = name.replace('/', ' ').replace('|', ' ').replace('\\', ' ').replace('?',
                                                                                   ' '). \
            replace('<', ' ').replace('>', ' ').replace('*', ' ').replace(':', ' ').replace('"', ' ').replace('-', ' ')
        if len(name) > max_len:
            return name[:max_len] + '.pdf'
        return name + '.pdf'

    def search_by_google_scholar(self, query, limit=10):
        """
        根据论文名称获得论文url 基于google scholar引擎

        """
        i = 0
        results = []

        while True:
            html = self.sess.request(method='GET', url=GOOGLE_SCHOLAR_URL + '?hl=zh-CN&q=' + query + '&start=' + str(i),
                                     headers={'User-Agent': ScholarConf.USER_AGENT}, verify=True, proxies=self.proxies)
            soup = BeautifulSoup(html.text, features='lxml')

            res_set = soup.find_all(
                lambda tag: tag.name == 'a' and tag.has_attr('id') and tag.has_attr('href')
                            and tag.has_attr('data-clk') and tag.has_attr('data-clk-atid') and tag.attrs[
                                'href'].startswith(
                    'http'), recursive=True)
            citations = soup.find_all(lambda tag: tag.name == 'span' and tag.has_attr('class') and tag.attrs[
                'class'][0] == 'gs_ct1' and tag.text == '[引用]', recursive=True)
            if not res_set:
                raise VerificationError("Error:google scholar 需要人机验证")
            for tag in res_set:
                info = self._get_paper_info(tag.attrs['href'])
                if info:
                    results.append(info)
                    if len(results) >= limit:
                        return results
            i += 10
            if len(res_set) + len(citations) < 10:  # 谷歌搜索不足10个条目
                break

        return results

    def check_download_url(self, url):
        """查看该链接是否可以直接下载"""
        try:
            response = self.sess.request(method='GET', url=url, headers={'User-Agent': ScholarConf.USER_AGENT},
                                         proxies=self.proxies, timeout=5.5)
            content_type_ = response.headers['Content-Type']
            if content_type_.find('text/html') < 0 and content_type_.find('application') >= 0:
                logger.info(url + '这是一个直接可以下载的链接！')
                return {'base_url': url, 'response': response}
        except Exception as e:
            return None
        return None

    async def async_get_direct_url(self, identifier, proxy=None):
        """
        异步获取scihub直链
        """

        async with aiohttp.ClientSession() as sess:
            async with sess.request(method='GET', url=self.base_url + identifier,
                                    headers={'User-Agent': ScholarConf.USER_AGENT}) as res:
                logger.info(f"获取 {self.base_url + identifier} 中...")
                # await 等待任务完成
                html = await res.text(encoding='utf-8')
                s = self._get_soup(html)
                frame = s.find('iframe') or s.find('embed')
                if frame:
                    return frame.get('src') if not frame.get('src').startswith('//') \
                        else 'http:' + frame.get('src')
                else:
                    logger.error("Error: 可能是 Scihub 上没有收录该文章, 请直接访问上述页面看是否正常。")
                    return html

    async def job(self, session, info, destination='', proxy=None, path=None):
        """
        异步下载文件
        """
        res = None
        try:
            url = info.url
            if url.startswith("/"):
                url = self.base_url.strip("/") + info.url
            logger.info("Downloading %s ...", url)
            url_handler = await session.get(url, proxy=proxy, headers=self._get_headers_for_url(url))
            res = await url_handler.read()
        except Exception as e:
            logger.error("Failed to download source file: %s", e)

        name = info.title

        if not res:
            return

        self._save(res,
                   os.path.join(destination, self._vaild_name(name)))

    async def async_download(self, loop, infos, destination='', proxy=None, path=None):
        """
        触发异步下载任务
        """
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600),
                                         headers={'User-Agent': ScholarConf.USER_AGENT}) as session:
            # 建立会话session
            tasks = [loop.create_task(self.job(session, info, destination, proxy, path)) for info in infos]
            # 建立所有任务
            finished, unfinished = await asyncio.wait(tasks)
            # 触发await，等待任务完成
            [r.result() for r in finished]

def main():
    setting = construct_download_setting()
    sh = SciHub(setting.proxy, dynamic_cookie=getattr(setting, 'dynamic_cookie', False))
    loop = asyncio.get_event_loop()
    infos = []
    for attr, value in vars(setting).items():  # 解析设定中的各个参数
        attr = attr[attr.rfind('__') + 2:]
        if attr in vars(DownLoadSetting).keys() or not value:
            continue

        if isinstance(setting, DownLoadCommandFileSetting):
            if 'bibtex' in attr:
                logger.info("info:开始从配置文件中指定的%s文件中下载..." % value[value.rfind('\\') + 1:])
                infos.extend(sh.generate_paper_info_by_bibtex(value))
            elif 'title' in attr:
                logger.info("info:开始从配置文件中指定的%s文件中下载..." % value[value.rfind('\\') + 1:])
                for title in readline_paper_info(value):
                    infos.extend(sh.search(setting.search_engine, title,
                                           limit=setting.limit,
                                           cookie=setting.cookie))
            else:
                logger.info("info:开始从配置文件中指定的%s文件中下载..." % value[value.rfind('\\') + 1:])
                infos.extend([sh._get_paper_info(input_) for input_ in readline_paper_info(value)])
        else:
            if 'words' == attr:
                logger.info("info:根据关键字%s开始搜索并下载..." % attr)
                infos.extend(sh.search(setting.search_engine, ' '.join(setting.words),
                                       limit=setting.limit,
                                       cookie=setting.cookie))
            else:
                logger.info("info:根据论文信息%s开始下载..." % attr)
                infos.append(sh._get_paper_info(value))
    infos = filter_none(infos)
    if len(infos) > 0:
        loop.run_until_complete(
            sh.async_download(asyncio.get_event_loop(), infos, setting.outputPath, proxy=setting.proxy))

if __name__ == '__main__':
    main()
