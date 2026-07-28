from __future__ import annotations

import hashlib
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import requests


class DomainRateLimiter:
    def __init__(self, requests_per_second: float = 0.5, sleep_fn=time.sleep, clock=time.monotonic):
        self.interval=1/max(requests_per_second,0.001);self.sleep_fn=sleep_fn;self.clock=clock
        self._locks={};self._last={};self._guard=threading.Lock()
    def wait(self,url:str):
        domain=urlsplit(url).netloc.casefold()
        with self._guard:lock=self._locks.setdefault(domain,threading.Lock())
        with lock:
            now=self.clock();delay=self.interval-(now-self._last.get(domain,0))
            if delay>0:self.sleep_fn(delay)
            self._last[domain]=self.clock()
    @contextmanager
    def slot(self,url:str):
        domain=urlsplit(url).netloc.casefold()
        with self._guard:lock=self._locks.setdefault(domain,threading.Lock())
        with lock:
            now=self.clock();delay=self.interval-(now-self._last.get(domain,0))
            if delay>0:self.sleep_fn(delay)
            self._last[domain]=self.clock()
            yield


class CrawlHTTPClient:
    def __init__(self,cache_dir,policy,session=None,sleep_fn=time.sleep):
        self.cache_dir=Path(cache_dir);self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.policy=policy;self.session=session;self._local=threading.local();self.sleep_fn=sleep_fn
        self.limiter=DomainRateLimiter(policy.get("requests_per_second_per_domain",0.5),sleep_fn=sleep_fn)
        self.headers={"User-Agent":"SleepAgent/0.1 metadata crawler (contact: jiawenjun1@gmail.com)","Accept":"text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.5"}
        if self.session is not None:self.session.headers.update(self.headers)
    def _session(self):
        if self.session is not None:return self.session
        if not hasattr(self._local,"session"):self._local.session=requests.Session();self._local.session.headers.update(self.headers)
        return self._local.session
    def _path(self,url):return self.cache_dir/f"{hashlib.sha256(url.encode()).hexdigest()}.cache"
    def get(self,url,*,use_cache=True,headers=None):
        path=self._path(url)
        if use_cache and path.exists():
            raw=path.read_bytes();head,body=raw.split(b"\n",1);return int(head),body,url,{"cached":True}
        last=None
        for attempt in range(self.policy.get("max_retries",2)+1):
            try:
                with self.limiter.slot(url):response=self._session().get(url,timeout=self.policy.get("timeout_seconds",20),allow_redirects=True,headers=headers)
                if response.status_code in {401,403,429,503} and attempt<self.policy.get("max_retries",2):
                    delay=float(response.headers.get("Retry-After",attempt+1)) if self.policy.get("respect_retry_after",True) else attempt+1
                    self.sleep_fn(min(delay,60));continue
                body=response.content
                if use_cache and response.status_code<400:path.write_bytes(str(response.status_code).encode()+b"\n"+body)
                return response.status_code,body,response.url,{"cached":False,"headers":dict(response.headers)}
            except requests.RequestException as exc:last=exc
        raise RuntimeError(f"HTTP request failed for {url}: {last}")
