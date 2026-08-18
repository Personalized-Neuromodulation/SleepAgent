# -*- coding: utf-8 -*-
import sys
import json
import logging
import time
import random
import re
import requests
from datetime import datetime, date
from urllib.parse import quote_plus, urljoin, urlparse
from dateutil import parser as dateparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

from .base import BaseParser
from .crossref_metadata import CrossrefMetadataFetcher

class PLOSParser(BaseParser):
    """PLOS期刊解析器 - 基于实际plos_requests_parser.py逻辑"""
    
    def __init__(self, paper_agent=None):
        super().__init__('plos', paper_agent)
        self.current_journal_info = {}
        self.issue_result_handler = None
        self.metadata_fetcher = CrossrefMetadataFetcher()
        
        # 初始化失败期刊记录
        self.failed_journals = []
        
        # PLOS期刊代码映射 - 必须在初始化时就定义，避免后续方法调用失败
        self.journal_code_to_path = {
            'PLOSOne': 'plosone',
            'PLOSBiology': 'plosbiology',
            'PLOSMedicine': 'plosmedicine',
            'PLOSGenetics': 'plosgenetics',
            'PLOSComputationalBiology': 'ploscompbiol',
            'PLOSPathogens': 'plospathogens',
            'PLOSNegTropicalDiseases': 'plosntds',
            'PLOSDigitalHealth': 'digitalhealth',
            'PLOSGlobalPublicHealth': 'globalpublichealth',
            'PLOSClimate': 'climate',
            'PLOSWater': 'water',
            'PLOSSustainabilityTransformation': 'sustainabilitytransformation',
            'PLOSComplexSystems': 'complexsystems',
            'PLOSMentalHealth': 'mentalhealth'
        }
        
        # 初始化失败期刊管理器
        from tools.failed_journals_manager import FailedJournalsManager
        self.failed_manager = FailedJournalsManager('plos')
        
        # PLOS专用用户代理
        self.plos_user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0'
        ]
        
        # 配置更长的重试和超时
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=10,  # 增加重试次数
            backoff_factor=8,  # 增加退避因子
            status_forcelist=[403, 429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def set_current_journal_info(self, journal_info):
        self.current_journal_info = journal_info or {}

    def set_issue_result_handler(self, handler):
        self.issue_result_handler = handler
    
    def _update_plos_journals_if_needed(self):
        """动态获取PLOS子刊URL列表，每次爬虫执行时更新JSON配置"""
        logger.info("开始动态获取PLOS期刊列表...")
        
        try:
            # 访问PLOS主域名获取期刊列表
            response = self.session.get('https://plos.org/', timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找期刊菜单容器
            menu_container = soup.find('div', class_='menu-journals-container')
            if not menu_container:
                logger.warning("未找到PLOS期刊菜单容器，使用现有配置")
                return
            
            # 获取期刊列表
            journal_links = menu_container.find_all('a', href=True)
            if not journal_links:
                logger.warning("未找到PLOS期刊链接，使用现有配置")
                return
            
            # 提取期刊信息
            new_journals = []
            for link in journal_links:
                href = link.get('href')
                name = link.get_text(strip=True)
                
                if href and 'journals.plos.org' in href and name.startswith('PLOS'):
                    # 确保URL以斜杠结尾
                    if not href.endswith('/'):
                        href += '/'
                    
                    new_journals.append({
                        'name': name,
                        'link': href
                    })
            
            logger.info(f"从PLOS主站动态获取到 {len(new_journals)} 个期刊")
            
            # 保存结果 - 只有获取到足够期刊时才使用智能更新器
            if len(new_journals) >= 10:
                # 使用智能更新器：只更新筛选期刊的链接，不添加新期刊
                try:
                    success = False
                    if success:
                        pass  # 智能更新器会输出详细信息
                    else:
                        logger.warning("智能更新失败，保留现有筛选配置不变")
                except Exception as e:
                    # 如果导入或执行失败，保留现有配置不变
                    logger.warning(f"智能更新器异常: {e}，保留现有筛选配置不变")
            else:
                logger.warning(f"获取的PLOS期刊数量不足 ({len(new_journals)}个)，保留现有配置")
                
        except Exception as e:
            logger.error(f"动态获取PLOS期刊列表失败: {e}")
            logger.info("将使用现有的PLOS期刊配置")
    
    def get_page_with_retry_plos(self, url, max_retries=8, timeout=60):
        """PLOS专用的请求重试方法，使用更长等待时间和重试次数"""
        for attempt in range(max_retries):
            try:
                # 轮换User-Agent
                user_agent = random.choice(self.plos_user_agents)
                self.session.headers['User-Agent'] = user_agent
                
                # 增加随机延迟避免被检测
                if attempt > 0:
                    delay = random.uniform(8, 20) * (attempt + 1)  # PLOS需要更长的延迟
                    logger.info(f"PLOS第{attempt + 1}次尝试前等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                
                logger.info(f"PLOS requests方式访问 {url} (第 {attempt + 1} 次)")
                response = self.session.get(url, timeout=timeout)
                
                if response.status_code == 200:
                    logger.info(f"PLOS成功获取页面: {url}")
                    return response
                elif response.status_code == 403:
                    logger.warning(f"PLOS收到403错误 (第 {attempt + 1} 次): {url}")
                    if attempt < max_retries - 1:
                        # 403错误时等待更长时间
                        time.sleep(random.uniform(15, 30))  # PLOS 403错误更长等待
                        continue
                else:
                    logger.warning(f"PLOS HTTP {response.status_code}: {url}")
                    
            except Exception as e:
                logger.warning(f"PLOS requests请求失败 (第 {attempt + 1} 次): {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(8, 15))  # PLOS更长的错误恢复时间
        
        logger.error(f"PLOS requests方式彻底失败: {url}")
        return None
    
    def should_use_topic_search(self):
        return False

    def scrape_journal(self, journal_name: str, base_url: str, start_date: datetime, end_date: datetime):
        """按issue模式爬取PLOS期刊数据。"""
        articles = self._scrape_crossref_batch(journal_name, start_date, end_date)
        if articles and self.issue_result_handler:
            logger.info(f"PLOS {journal_name}: Crossref batch ready {len(articles)} papers, callback")
            self.issue_result_handler(articles, "Crossref metadata")
            return []
        return articles
    


    def scrape_journal_stream(
            self,
            journal_name: str,
            base_url: str,
            start_date,
            end_date,
            callback=None
    ):
        """PLOS按Crossref metadata流式处理。"""

        articles = self._scrape_crossref_batch(journal_name, start_date, end_date)
        if articles and callback:
            logger.info(f"PLOS {journal_name}: Crossref batch ready {len(articles)} papers, callback")
            callback(articles)
        return articles

        logger.info(f"PLOS {journal_name}: stream开始")

        def save_page(page_articles):
            if not page_articles:
                return

            logger.info(
                f"PLOS {journal_name}: 当前批次完成 {len(page_articles)} 篇，执行callback"
            )

            if callback:
                callback(page_articles)

        try:
            logger.info(f"PLOS {journal_name}: 直接进入issue模式")
            fallback_parser = PLOSFallbackParser(main_parser=self)

            try:
                fallback_parser.scrape_journal_fallback(
                    journal_name,
                    base_url,
                    start_date,
                    end_date,
                    callback=save_page
                )

            finally:
                fallback_parser.close()

        except Exception as e:
            logger.error(
                f"PLOS {journal_name}: stream失败 {e}"
            )
            raise


    def _scrape_with_fallback_logic(self, journal_name: str, base_url: str, start_date: datetime, end_date: datetime, callback=None):
        """PLOS备选爬取逻辑 - 通过volume页面"""
        fallback_parser = PLOSFallbackParser(main_parser=self)
        try:
            articles = fallback_parser.scrape_journal_fallback(journal_name, base_url, start_date, end_date, callback=callback)
            return articles
        finally:
            fallback_parser.close()

    def _scrape_crossref_batch(self, journal_name, start_date, end_date):
        issns = self._get_current_issns()
        if not issns:
            logger.info(f"PLOS {journal_name}: CSV missing ISSN/EISSN; Crossref skipped")
            return []

        logger.info(
            f"PLOS {journal_name}: Crossref only issn={','.join(issns)} "
            f"keywords=disabled range={start_date}..{end_date}"
        )
        rows = self.metadata_fetcher.fetch_by_issn(
            issns=issns,
            start_date=start_date,
            end_date=end_date,
            keywords=None,
            journal_name=journal_name,
        )
        if not rows:
            logger.info(f"PLOS {journal_name}: Crossref returned 0 articles")
            return []

        deduped = self._dedupe_metadata_by_doi(rows)
        date_kept = []
        date_filtered = 0
        for row in deduped:
            article_date = row.get("date")
            if article_date and not self._is_date_in_range(article_date, start_date, end_date):
                date_filtered += 1
                continue
            date_kept.append(self._normalize_article(row, journal_name))

        for article in date_kept:
            article["quality_score"] = self.validate_article(article)

        for item in self._iter_keyword_stats():
            logger.info(
                f"PLOS {journal_name}: keyword='{item.get('keyword', '') or 'ALL'}' "
                f"fetched={item.get('fetched', 0)} added={item.get('added', 0)}"
            )
        logger.info(
            f"PLOS {journal_name}: Crossref batch candidate={len(rows)}, "
            f"deduped={len(deduped)}, date_filtered={date_filtered}, metadata_kept={len(date_kept)}"
        )
        return date_kept

    def _get_current_issns(self):
        source_row = {}
        if isinstance(self.current_journal_info, dict):
            source_row = self.current_journal_info.get("source_row") or {}

        values = []
        for container in (self.current_journal_info or {}, source_row):
            for key, value in (container or {}).items():
                normalized_key = str(key or "").strip().lower().replace("-", "").replace("_", "")
                if normalized_key in ("issn", "eissn", "printissn", "onlineissn"):
                    values.append(value)

        issns = []
        for value in values:
            for part in re.split(r"[;,/|\s]+", str(value or "")):
                compact = part.strip().upper().replace("-", "")
                if re.match(r"^\d{7}[\dX]$", compact):
                    formatted = f"{compact[:4]}-{compact[4:]}"
                    if formatted not in issns:
                        issns.append(formatted)
        return issns

    def _iter_keyword_stats(self):
        stats = getattr(self.metadata_fetcher, "last_keyword_stats", [])
        if isinstance(stats, dict):
            for keyword, item in stats.items():
                row = dict(item or {})
                row.setdefault("keyword", keyword)
                yield row
            return
        if isinstance(stats, list):
            for item in stats:
                if isinstance(item, dict):
                    yield item

    def _dedupe_metadata_by_doi(self, rows):
        seen = set()
        deduped = []
        for row in rows or []:
            doi = str(row.get("doi") or "").strip().lower()
            if not doi or doi in seen:
                continue
            seen.add(doi)
            deduped.append(row)
        return deduped

    def _normalize_article(self, row, journal_name):
        article = dict(row or {})
        doi = str(article.get("doi") or "").strip()
        if doi:
            article["doi"] = doi
            article.setdefault("url", f"https://doi.org/{doi}")
        article.setdefault("journal", journal_name)
        article.setdefault("title", "")
        article.setdefault("abstract", "")
        article.setdefault("authors", "")
        article.setdefault("article_type", article.get("type", ""))
        article["source"] = article.get("source") or "crossref"
        return article

    def validate_article(self, article):
        if not article:
            return 0
        score = 0
        if article.get("title"):
            score += 20
        if article.get("doi"):
            score += 30
        if article.get("abstract"):
            score += 30
        if article.get("date"):
            score += 20
        return score
    
    def _get_plos_journal_path(self, journal_name):
        """获取PLOS期刊路径"""
        return self.journal_code_to_path.get(journal_name, 'plosone')
    
    def _get_plos_article_details(self, doi_url):
        """获取PLOS文章详情"""
        try:
            response = self.session.get(doi_url, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 标题: <h1 id="title" class="title">
                title_elem = soup.find('h1', id='title', class_='title') or soup.find('h1', class_='title')
                title = title_elem.get_text(strip=True) if title_elem else ''
                
                # 获取摘要/Introduction
                abstract = ''
                # 先尝试获取摘要
                abstract_elem = soup.find('div', class_='abstract') or \
                              soup.find('div', id='abstract') or \
                              soup.find('section', class_='abstract')
                
                if abstract_elem:
                    abstract = abstract_elem.get_text(strip=True)
                
                # 如果没有摘要，尝试获取Introduction
                if not abstract:
                    intro_elem = soup.find('div', class_='introduction') or \
                               soup.find('section', class_='introduction')
                    if intro_elem:
                        abstract = intro_elem.get_text(strip=True)[:500] + "..."
                
                # 获取DOI
                doi = doi_url.split('/')[-1] if '/' in doi_url else ''
                
                # 日期: <time class="published">August 20, 2025</time>
                pub_date = datetime.now().date()
                date_elem = soup.find('time', class_='published')
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                    try:
                        pub_date = dateparser.parse(date_text).date()
                    except:
                        pass
                else:
                    # 备用方案：meta标签
                    meta_date_elem = soup.find('meta', attrs={'name': 'citation_publication_date'})
                    if meta_date_elem:
                        try:
                            pub_date = dateparser.parse(meta_date_elem.get('content')).date()
                        except:
                            pass
                
                # 作者信息
                authors = ''
                author_elems = soup.find_all('meta', attrs={'name': 'citation_author'})
                if author_elems:
                    authors = '; '.join([elem.get('content', '') for elem in author_elems])
                
                return {
                    'title': title,
                    'abstract': abstract,
                    'doi': doi,
                    'url': doi_url,
                    'date': pub_date,
                    'authors': authors
                }
                
        except Exception as e:
            logger.error(f"获取PLOS文章详情失败: {e}")
        
        return None
    
    def _get_plos_article_details_from_page(self, article_url, max_retries=8, timeout=60):
        """基于文章页面URL获取PLOS文章详情，根据用户截图优化"""
        try:
            # 使用增强的重试机制
            response = self.get_page_with_retry_plos(article_url, max_retries=max_retries, timeout=timeout)
            if not response:
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 标题: 基于截图中的结构
            title = ''
            title_selectors = [
                'h1#artTitle',  # 截图中看到的ID
                'div.title-authors h1',  # 截图中的结构  
                'div.article-title-etc h1',  # 从截图看到的结构
                'h1.title',
                'h1#title',
                'h1'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    logger.debug(f"PLOS标题提取成功，使用选择器: {selector}")
                    break
            
            # 摘要: 基于截图中的结构
            abstract = ''
            abstract_selectors = [
                'div.article-content div#artText p',  # 截图中的抽象内容结构
                'div.abstract-content',
                'section.abstract',
                'div#abstract',
                'div.abstract'
            ]
            
            for selector in abstract_selectors:
                abstract_elem = soup.select_one(selector)
                if abstract_elem:
                    abstract = abstract_elem.get_text(strip=True)
                    break
            
            # 如果没有找到摘要，尝试查找Introduction部分
            if not abstract:
                intro_selectors = [
                    'div.article-content p',
                    'div.article-text p',
                    '.introduction p'
                ]
                for selector in intro_selectors:
                    intro_elems = soup.select(selector)
                    if intro_elems:
                        # 取前几段作为摘要
                        abstract = ' '.join([p.get_text(strip=True) for p in intro_elems[:3]])
                        if len(abstract) > 500:
                            abstract = abstract[:500] + "..."
                        break
            
            # DOI: 从URL中提取
            doi = ''
            if 'id=' in article_url:
                doi = article_url.split('id=')[-1]
            
            # 日期: 基于截图中的结构优化 
            pub_date = None  # 不设置默认日期，留给后续处理
            date_selectors = [
                'li#artPubDate',  # 截图中清楚看到的ID: Published: September 3, 2025
                'ul.date-doi li#artPubDate',  # 完整的层级路径
                'ul.date-doi li',
                'time.published',
                '.pub-date',
                'meta[name="citation_publication_date"]',  # meta标签日期
                'meta[name="DC.date"]'  # Dublin Core日期
            ]
            
            for selector in date_selectors:
                try:
                    if selector.startswith('meta'):
                        date_elem = soup.find('meta', attrs={'name': selector.split('[name="')[1].split('"]')[0]})
                        if date_elem:
                            date_text = date_elem.get('content', '').strip()
                        else:
                            continue
                    else:
                        date_elem = soup.select_one(selector)
                        if date_elem:
                            date_text = date_elem.get_text(strip=True)
                        else:
                            continue
                    
                    # 清理日期文本
                    date_text = date_text.replace('Published:', '').replace('published', '').strip()
                    
                    if date_text:
                        parsed_date = dateparser.parse(date_text)
                        if parsed_date:
                            pub_date = parsed_date.date()
                            logger.debug(f"PLOS日期解析成功，使用选择器: {selector}, 日期: {pub_date}")
                            break
                        else:
                            logger.debug(f"PLOS日期解析失败，选择器: {selector}, 无法解析: {date_text}")
                    
                except Exception as date_error:
                    logger.debug(f"PLOS日期解析异常，选择器: {selector}, 错误: {date_error}")
                    continue
            
            # 如果从详情页面没有找到日期，尝试从摘要或Introduction部分查找
            if not pub_date:
                logger.debug("详情页面未找到日期，尝试从摘要和Introduction查找")
                content_selectors = [
                    'div.article-content div#artText',  # 截图中的文章内容区域
                    'div.abstract-content',
                    'section.abstract',
                    'div#abstract',
                    'div.abstract',
                    'div.article-text',
                    '.introduction'
                ]
                
                for content_selector in content_selectors:
                    try:
                        content_elem = soup.select_one(content_selector)
                        if content_elem:
                            content_text = content_elem.get_text()
                            # 查找日期模式
                            import re
                            date_patterns = [
                                r'Published:\s*([A-Za-z]+ \d{1,2}, \d{4})',
                                r'published\s*([A-Za-z]+ \d{1,2}, \d{4})',
                                r'(\d{4}-\d{2}-\d{2})',
                                r'([A-Za-z]+ \d{1,2}, \d{4})'
                            ]
                            
                            for pattern in date_patterns:
                                match = re.search(pattern, content_text, re.IGNORECASE)
                                if match:
                                    date_text = match.group(1)
                                    try:
                                        parsed_date = dateparser.parse(date_text)
                                        if parsed_date:
                                            pub_date = parsed_date.date()
                                            logger.debug(f"PLOS从内容中找到日期: {pub_date}")
                                            break
                                    except:
                                        continue
                            if pub_date:
                                break
                    except Exception as e:
                        logger.debug(f"从内容查找日期失败: {e}")
                        continue
            
            # 如果仍然没有日期，设置为None而不是默认日期
            if not pub_date:
                logger.warning(f"PLOS文章日期解析完全失败，设置为None: {article_url}")
                pub_date = None
            
            # 作者信息: 基于截图中的结构优化
            authors = ''
            # 方法1: meta标签
            author_elems = soup.find_all('meta', attrs={'name': 'citation_author'})
            if author_elems:
                authors = '; '.join([elem.get('content', '') for elem in author_elems])
                logger.debug(f"PLOS作者信息从meta标签获取: {len(author_elems)}个作者")
            else:
                # 方法2: 基于截图中的页面结构
                author_selectors = [
                    'ul.author-list li a[data-author-id]',  # 截图中清楚显示的结构
                    'li[data-js-tooltip="tooltip_trigger"] a[data-author-id]',  # 更精确的截图结构
                    'div.title-authors ul.author-list li a',  # 从截图看到的层级
                    'div.title-authors .author-list',
                    '.author-names',
                    '.contributors'
                ]
                for selector in author_selectors:
                    if 'a[data-author-id]' in selector:
                        # 处理链接元素
                        author_links = soup.select(selector)
                        if author_links:
                            author_names = [link.get_text(strip=True) for link in author_links if link.get_text(strip=True)]
                            if author_names:
                                authors = ', '.join(author_names)
                                logger.debug(f"PLOS作者信息从链接获取: {selector}, {len(author_names)}个作者")
                                break
                    else:
                        # 处理容器元素
                        author_elem = soup.select_one(selector)
                        if author_elem:
                            authors = author_elem.get_text(strip=True)
                            logger.debug(f"PLOS作者信息从容器获取: {selector}")
                            break
            
            # 验证关键字段
            if not title:
                return None
                
            article_data = {
                'title': title,
                'abstract': abstract if abstract else '摘要未找到',
                'doi': doi,
                'url': article_url,
                'date': pub_date,
                'authors': authors if authors else '作者未找到'
            }
            
            return article_data
            
        except Exception as e:
            logger.error(f"获取PLOS文章详情失败 ({article_url}): {e}")
        
        return None

    
    def close(self):
        """关闭资源"""
        self.close_browser()
        
        if self.session:
            try:
                self.session.close()
                logger.info("PLOS Requests session已关闭")
            except Exception as e:
                logger.error(f"关闭PLOS requests session失败: {e}")


class PLOSFallbackParser:
    """PLOS fallback crawler based on journal /volume issue pages."""

    def __init__(self, main_parser=None):
        self.main_parser = main_parser
        self.session = requests.Session()
        if main_parser:
            self.session.headers.update(main_parser.session.headers)
        else:
            self.session.headers.update({
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            })

    def scrape_journal_fallback(
            self,
            journal_name: str,
            base_url: str,
            start_date: datetime,
            end_date: datetime,
            callback=None
    ):
        """
        fallback分页流式模式:

        issue1
          -> parse
          -> callback保存

        issue2
          -> parse
          -> callback保存
        """

        logger.info(f"PLOS fallback start: {journal_name}")

        try:
            if isinstance(start_date, datetime):
                start_date = start_date.date()

            if isinstance(end_date, datetime):
                end_date = end_date.date()

            volume_url = base_url.rstrip('/') + '/volume'

            logger.info(
                f"PLOS fallback volume URL: {volume_url}"
            )

            soup = self._get_soup_with_playwright_fallback(volume_url)

            issue_links = self._extract_issue_links(
                soup,
                start_date,
                end_date
            )

            logger.info(
                f"PLOS fallback found {len(issue_links)} issue pages"
            )

            total = 0

            for issue_info in issue_links:

                issue_url = issue_info['url']
                issue_date = issue_info['date']

                logger.info(
                    f"PLOS fallback issue: {issue_date} - {issue_url}"
                )

                issue_articles = self._scrape_issue_page(
                    issue_url,
                    journal_name,
                    start_date,
                    end_date
                )

                if issue_articles:

                    total += len(issue_articles)

                    logger.info(
                        f"PLOS fallback issue完成 {len(issue_articles)}篇，立即callback"
                    )

                    if callback:
                        callback(issue_articles)

                # 防止长期连续请求
                time.sleep(random.uniform(1,2))


            logger.info(
                f"PLOS fallback completed: {journal_name}, articles={total}"
            )

            return []

        except Exception as e:
            logger.error(
                f"PLOS fallback failed: {journal_name} - {e}"
            )
            return []


    def _extract_issue_links(self, soup, start_date, end_date):
        issue_links = []

        try:
            year_elements = soup.find_all(
                ['button', 'a', 'span', 'div'],
                string=lambda text: (
                    text
                    and text.strip().isdigit()
                    and len(text.strip()) == 4
                    and int(text.strip()) >= 2005
                )
            )
            year_buttons = []
            for elem in year_elements:
                year = int(elem.get_text(strip=True))
                if start_date.year <= year <= end_date.year:
                    year_buttons.append((year, elem))

            if not year_buttons:
                year_buttons = [(int(elem.get_text(strip=True)), elem) for elem in year_elements]

            for year, _ in year_buttons:
                year_container = soup.find('li', id=str(year))
                if not year_container:
                    year_container = next(
                        (container for container in soup.find_all('li', class_='slide') if container.get('id') == str(year)),
                        None
                    )
                if not year_container:
                    logger.debug(f"PLOS fallback did not find issue container for year {year}")
                    continue

                for link in year_container.find_all('a', href=True):
                    month_span = link.find('span')
                    if not month_span:
                        continue
                    month_name = month_span.get_text(strip=True)
                    month_num = self._month_name_to_number(month_name)
                    if month_num is None:
                        logger.debug(f"PLOS fallback skipped unknown month: {month_name}")
                        continue

                    try:
                        issue_date = date(year, month_num, 1)
                    except ValueError:
                        continue

                    if not self._is_issue_in_range(issue_date, start_date, end_date):
                        continue

                    issue_links.append({
                        'url': urljoin('https://journals.plos.org', link.get('href')),
                        'date': issue_date,
                        'year': year,
                        'month': month_name,
                    })

            issue_links.sort(key=lambda item: item['date'], reverse=True)
        except Exception as e:
            logger.error(f"PLOS fallback issue-link extraction failed: {e}")

        return issue_links

    def _month_name_to_number(self, month_name):
        month_mapping = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4,
            'May': 5, 'June': 6, 'July': 7, 'August': 8,
            'September': 9, 'October': 10, 'November': 11, 'December': 12,
        }
        return month_mapping.get(month_name.capitalize())

    def _is_issue_in_range(self, issue_date, start_date, end_date):
        issue_month_start = issue_date.replace(day=1)
        if issue_date.month == 12:
            issue_month_end = issue_date.replace(year=issue_date.year + 1, month=1, day=1)
        else:
            issue_month_end = issue_date.replace(month=issue_date.month + 1, day=1)
        return not (issue_month_end <= start_date or issue_month_start > end_date)

    def _get_soup_with_playwright_fallback(self, url):
        try:
            logger.info(f"PLOS fallback requests访问: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            if response.text and len(response.text.strip()) > 100:
                return BeautifulSoup(response.text, 'html.parser')
            logger.warning(f"PLOS fallback requests内容无效，切换Playwright: {url}")
        except Exception as e:
            logger.warning(f"PLOS fallback requests失败，切换Playwright: {url} - {e}")

        if self.main_parser:
            try:
                logger.info(f"PLOS fallback Playwright访问: {url}")
                html = self.main_parser.fetch_html_with_playwright(url, max_wait=30, settle_seconds=2)
                if html:
                    return BeautifulSoup(html, 'html.parser')
            except Exception as e:
                logger.warning(f"PLOS fallback Playwright失败: {url} - {e}")

        raise RuntimeError(f"PLOS fallback unable to fetch page: {url}")

    def _scrape_issue_page(self, issue_url, journal_name, start_date, end_date):
        articles = []
        try:
            soup = self._get_soup_with_playwright_fallback(issue_url)

            for section in soup.find_all('div', class_='section'):
                for item in section.find_all('div', class_='item cf'):
                    article_info = self._extract_article_from_item(item, journal_name)
                    if not article_info:
                        continue

                    article_date = article_info.get('date')
                    if isinstance(article_date, date) and not (start_date <= article_date <= end_date):
                        continue

                    articles.append(article_info)
                    logger.info(f"PLOS fallback article: {article_info.get('title', 'Unknown')[:80]}")
        except Exception as e:
            logger.error(f"PLOS fallback issue scrape failed: {issue_url} - {e}")

        return articles

    def _extract_article_from_item(self, item, journal_name):
        try:
            title_elem = item.find('h3', class_='item--article-title')
            title_link = title_elem.find('a', href=True) if title_elem else None
            if not title_link:
                return None

            title = title_link.get_text(strip=True)
            article_url = urljoin('https://journals.plos.org', title_link.get('href'))

            doi = None
            article_info_elem = item.find('p', class_='article-info')
            if article_info_elem:
                doi_link = article_info_elem.find('a', href=True)
                if doi_link and 'doi.org' in doi_link.get('href', ''):
                    doi = doi_link.get('href')

            pub_date = None
            if article_info_elem:
                date_span = article_info_elem.find('span', class_='article-info--date')
                if date_span:
                    date_text = date_span.get_text(strip=True).replace('published', '').strip()
                    try:
                        pub_date = dateparser.parse(date_text).date()
                    except Exception:
                        logger.debug(f"PLOS fallback date parse failed: {date_text}")

            authors_elem = item.find('p', class_='authors')
            authors = authors_elem.get_text(strip=True) if authors_elem else ''

            abstract = ''
            if self.main_parser and hasattr(self.main_parser, '_get_plos_article_details_from_page'):
                try:
                    detailed_info = self.main_parser._get_plos_article_details_from_page(article_url)
                    if detailed_info:
                        abstract = detailed_info.get('abstract', '')
                        if not pub_date and detailed_info.get('date'):
                            pub_date = detailed_info['date']
                except Exception as e:
                    logger.debug(f"PLOS fallback detail fetch failed: {e}")

            return {
                'title': title,
                'abstract': abstract,
                'doi': doi or article_url,
                'url': article_url,
                'date': pub_date or date.today(),
                'journal': journal_name,
                'authors': authors,
                'type': 'fallback',
            }
        except Exception as e:
            logger.error(f"PLOS fallback article extraction failed: {e}")
            return None

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

