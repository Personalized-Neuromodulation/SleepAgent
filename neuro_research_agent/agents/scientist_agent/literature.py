from __future__ import annotations

import json
import re
import time
from typing import Any
from xml.etree import ElementTree

import requests


def tokenize(text: str) -> set[str]:
    return {tok.lower() for tok in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", text)}


def score_item(prompt_tokens: set[str], item: dict[str, Any]) -> int:
    tokens = tokenize(" ".join([item.get("title", ""), item.get("finding", ""), " ".join(item.get("keywords", [])), item.get("topic", "")]))
    return len(prompt_tokens & tokens)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _paper_key(paper: dict[str, Any]) -> str:
    doi = _clean_text(paper.get("doi")).lower()
    if doi:
        return f"doi:{doi}"
    url = _clean_text(paper.get("url")).lower()
    if url:
        return f"url:{url}"
    return f"title:{_clean_text(paper.get('title')).lower()}"


def search_semantic_scholar(prompt: str, max_papers: int = 20, timeout: int = 10) -> list[dict[str, Any]]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": prompt, "limit": min(max_papers, 25), "fields": "title,abstract,year,url,authors,citationCount,venue,externalIds"}
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    papers = []
    for item in response.json().get("data", []):
        external_ids = item.get("externalIds") or {}
        papers.append(
            {
                "title": _clean_text(item.get("title")),
                "finding": _clean_text(item.get("abstract"))[:1200],
                "url": _clean_text(item.get("url")),
                "year": item.get("year"),
                "venue": _clean_text(item.get("venue")),
                "citation_count": item.get("citationCount", 0),
                "authors": [_clean_text(author.get("name")) for author in item.get("authors", []) if _clean_text(author.get("name"))],
                "doi": _clean_text(external_ids.get("DOI")),
                "source": "semantic_scholar",
            }
        )
    return papers


def search_crossref(prompt: str, max_papers: int = 20, timeout: int = 10) -> list[dict[str, Any]]:
    url = "https://api.crossref.org/works"
    params = {
        "query": prompt,
        "rows": min(max_papers, 25),
        "select": "title,abstract,published-print,published-online,container-title,URL,author,DOI,is-referenced-by-count",
    }
    headers = {"User-Agent": "neuroscience-research-agent/1.0 (mailto:research@example.com)"}
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    papers = []
    for item in response.json().get("message", {}).get("items", []):
        title_values = item.get("title") or []
        title = _clean_text(title_values[0] if title_values else "")
        if not title:
            continue
        published = item.get("published-print") or item.get("published-online") or {}
        date_parts = published.get("date-parts") or []
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        venue_values = item.get("container-title") or []
        authors = []
        for author in item.get("author") or []:
            name = _clean_text(" ".join(part for part in [author.get("given"), author.get("family")] if part))
            if name:
                authors.append(name)
        papers.append(
            {
                "title": title,
                "finding": _clean_text(re.sub(r"<[^>]+>", " ", item.get("abstract") or ""))[:1200],
                "url": _clean_text(item.get("URL")),
                "year": year,
                "venue": _clean_text(venue_values[0] if venue_values else ""),
                "citation_count": int(item.get("is-referenced-by-count") or 0),
                "authors": authors,
                "doi": _clean_text(item.get("DOI")),
                "source": "crossref",
            }
        )
    return papers


def search_arxiv(prompt: str, max_papers: int = 20, timeout: int = 15) -> list[dict[str, Any]]:
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{prompt}",
        "start": 0,
        "max_results": min(max_papers, 25),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    papers = []
    for entry in root.findall("atom:entry", ns):
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        if not title:
            continue
        authors = [_clean_text(author.findtext("atom:name", default="", namespaces=ns)) for author in entry.findall("atom:author", ns)]
        published = _clean_text(entry.findtext("atom:published", default="", namespaces=ns))
        year = int(published[:4]) if published[:4].isdigit() else None
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = _clean_text(link.attrib.get("href"))
                break
        doi = _clean_text(entry.findtext("arxiv:doi", default="", namespaces=ns))
        papers.append(
            {
                "title": title,
                "finding": _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))[:1200],
                "url": _clean_text(entry.findtext("atom:id", default="", namespaces=ns)),
                "pdf_url": pdf_url,
                "year": year,
                "venue": "arXiv",
                "citation_count": 0,
                "authors": [author for author in authors if author],
                "doi": doi,
                "source": "arxiv",
            }
        )
    return papers


def ollama_model(base_url: str, configured_model: str, timeout: int = 5) -> str:
    if configured_model:
        return configured_model
    response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
    response.raise_for_status()
    models = response.json().get("models", [])
    if not models:
        raise RuntimeError("Ollama has no installed models.")
    return str(models[0].get("name", ""))


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        payload = json.loads(match.group(0))
    return payload if isinstance(payload, dict) else {}


def call_ollama_json(base_url: str, configured_model: str, system_prompt: str, user_prompt: str, timeout: int = 90) -> dict[str, Any]:
    model = ollama_model(base_url, configured_model)
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = parse_json_object(str(response.json().get("response", "")))
    payload["_ollama_model"] = model
    return payload


def plan_literature_queries(prompt: str, max_papers: int, allow_network: bool, ollama_url: str, ollama_model_name: str) -> dict[str, Any]:
    system_prompt = (
        "You are a neuroscience literature search planner. Return JSON only. "
        "Create focused English keywords and search queries for the user's research task. "
        "Schema: {\"keywords\": [string], \"queries\": [string], \"rationale_zh\": string}. "
        "Use 5 to 8 keywords and 3 to 5 queries. Include modality, analysis method, experiment design, and outcome terms when relevant."
    )
    user_prompt = f"用户研究任务：{prompt}\n目标最终文献数：{max_papers}\n允许联网检索：{allow_network}"
    payload = call_ollama_json(ollama_url, ollama_model_name, system_prompt, user_prompt)
    keywords = [str(item).strip() for item in payload.get("keywords", []) if str(item).strip()]
    queries = [str(item).strip() for item in payload.get("queries", []) if str(item).strip()]
    if prompt not in queries:
        queries.insert(0, prompt)
    payload["keywords"] = keywords[:8]
    payload["queries"] = queries[:5]
    return payload


def deduplicate_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for paper in papers:
        key = _paper_key(paper)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(paper)
    return deduped


def _merge_search_terms(plan: dict[str, Any], prompt: str) -> list[str]:
    terms: list[str] = []
    for item in [prompt, *plan.get("keywords", []), *plan.get("queries", [])]:
        term = _clean_text(item)
        if term and term.lower() not in {existing.lower() for existing in terms}:
            terms.append(term)
    return terms[:8]


def initial_literature_search(plan: dict[str, Any], prompt: str, max_papers: int, allow_network: bool) -> tuple[list[dict[str, Any]], list[str], dict[str, int]]:
    if not allow_network:
        raise RuntimeError("文献资料检索必须联网执行；当前 allow_network=False。")
    pool: list[dict[str, Any]] = []
    errors: list[str] = []
    source_counts = {"arxiv": 0, "crossref": 0, "semantic_scholar": 0}
    terms = _merge_search_terms(plan, prompt)
    per_source_limit = max(5, min(25, max_papers // max(1, len(terms)) + 5))
    searchers = [
        ("arxiv", search_arxiv),
        ("crossref", search_crossref),
        ("semantic_scholar", search_semantic_scholar),
    ]
    for term in terms:
        for source_name, searcher in searchers:
            try:
                results = searcher(term, max_papers=per_source_limit)
                source_counts[source_name] += len(results)
                for item in results:
                    item["search_query"] = term
                    item["retrieval_source"] = source_name
                pool.extend(results)
                time.sleep(0.8 if source_name == "semantic_scholar" else 0.25)
            except Exception as exc:
                errors.append(f"{source_name} | {term}: {type(exc).__name__}: {exc}")
                if source_name == "semantic_scholar" and "429" in str(exc):
                    time.sleep(5)
    return deduplicate_papers(pool), errors, source_counts


def deterministic_screen_online_papers(prompt: str, papers: list[dict[str, Any]], max_papers: int) -> list[dict[str, Any]]:
    prompt_tokens = tokenize(prompt)
    ranked = sorted(papers, key=lambda item: (score_item(prompt_tokens, item), int(item.get("citation_count") or 0)), reverse=True)
    screened = []
    for idx, paper in enumerate(ranked[:max_papers], start=1):
        relevance = score_item(prompt_tokens, paper)
        screened.append(
            paper
            | {
                "rank": idx,
                "relevance_score": relevance,
                "evidence_quality": "medium",
                "evidence_quality_reason_zh": "基于联网检索候选文献的关键词匹配和引用数进行确定性评价。",
                "summary_zh": paper.get("finding", "")[:260],
                "key_contribution_zh": "为当前研究任务提供相关背景或方法依据。",
                "limitations_zh": "未经过 LLM 深度筛选；需要人工阅读原文确认。",
            }
        )
    return screened


def llm_screen_papers(prompt: str, papers: list[dict[str, Any]], max_papers: int, ollama_url: str, ollama_model_name: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    compact = []
    for idx, paper in enumerate(papers[: max(max_papers * 3, max_papers)], start=1):
        compact.append(
            {
                "index": idx,
                "title": paper.get("title", ""),
                "abstract": paper.get("finding", "")[:900],
                "year": paper.get("year"),
                "venue": paper.get("venue", ""),
                "citation_count": paper.get("citation_count", 0),
                "source": paper.get("source", ""),
                "retrieval_source": paper.get("retrieval_source", ""),
            }
        )
    system_prompt = (
        "You are a rigorous neuroscience literature review agent. Return JSON only. "
        "Select source papers that can support innovative experiments for the user's task. "
        "Prefer papers with clear methods, measurable outputs, and direct relevance to neuroscience data analysis. "
        "Compress each abstract in Chinese and judge evidence quality. "
        "Schema: {\"selected\": [{\"index\": integer, "
        "\"relevance_score\": integer, \"evidence_quality\": \"high\"|\"medium\"|\"low\", "
        "\"evidence_quality_reason_zh\": string, \"summary_zh\": string, "
        "\"key_contribution_zh\": string, \"limitations_zh\": string, "
        "\"usage_zh\": string, \"support_type\": \"methodological\"|\"conceptual\"|\"dataset\"|\"validation\"|\"clinical\"}], "
        "\"overall_assessment_zh\": string}. "
        "relevance_score must be 0-100. Select at most the requested number of papers."
    )
    user_prompt = json.dumps(
        {"research_task": prompt, "max_selected_papers": max_papers, "candidate_papers": compact},
        ensure_ascii=False,
    )
    payload = call_ollama_json(ollama_url, ollama_model_name, system_prompt, user_prompt, timeout=120)
    selected = []
    by_index = {idx: paper for idx, paper in enumerate(papers[: max(max_papers * 3, max_papers)], start=1)}
    for rank, item in enumerate(payload.get("selected", []), start=1):
        try:
            source_paper = by_index[int(item.get("index"))]
        except Exception:
            continue
        selected.append(
            source_paper
            | {
                "rank": rank,
                "relevance_score": int(item.get("relevance_score", 0) or 0),
                "evidence_quality": str(item.get("evidence_quality", "medium")),
                "evidence_quality_reason_zh": str(item.get("evidence_quality_reason_zh", "")),
                "summary_zh": str(item.get("summary_zh", "")),
                "key_contribution_zh": str(item.get("key_contribution_zh", "")),
                "limitations_zh": str(item.get("limitations_zh", "")),
                "usage_zh": str(item.get("usage_zh", "")),
                "support_type": str(item.get("support_type", "methodological")),
            }
        )
    if not selected:
        selected = deterministic_screen_online_papers(prompt, papers, max_papers)
    if len(selected) < min(max_papers, len(papers)):
        selected_keys = {(item.get("url") or item.get("title") or "").lower().strip() for item in selected}
        supplemental = deterministic_screen_online_papers(prompt, papers, max_papers)
        for item in supplemental:
            key = (item.get("url") or item.get("title") or "").lower().strip()
            if key and key not in selected_keys:
                item["screening_note_zh"] = "LLM 未选入但用户请求更多文献，已按关键词相关性和引用数补充。"
                selected.append(item)
                selected_keys.add(key)
            if len(selected) >= max_papers:
                break
        for rank, item in enumerate(selected, start=1):
            item["rank"] = rank
        payload["supplemented_to_requested_count"] = True
        payload["final_selected_count"] = len(selected)
    return selected[:max_papers], payload


def build_chinese_literature_report(prompt: str, plan: dict[str, Any], papers: list[dict[str, Any]], llm_payload: dict[str, Any], allow_network: bool) -> str:
    lines = [
        "# 中文文献检索报告",
        "",
        f"## 研究任务",
        "",
        prompt,
        "",
        "## 检索设置",
        "",
        f"- 允许联网检索：{'是' if allow_network else '否'}",
        f"- 检索规划模型：{plan.get('_ollama_model', 'unavailable')}",
        f"- 检索关键词：{', '.join(plan.get('keywords', []))}",
        f"- 检索查询：{', '.join(plan.get('queries', []))}",
        f"- 检索策略说明：{plan.get('rationale_zh', '先由 LLM 生成关键词，再进行 arXiv/Crossref/Semantic Scholar 多源联网检索。')}",
        "",
        "## 总体判断",
        "",
        str(llm_payload.get("overall_assessment_zh", "根据相关性、摘要内容和证据质量筛选文献。")),
        "",
        "## 入选文献",
        "",
    ]
    for paper in papers:
        authors = ", ".join(paper.get("authors", [])[:3]) if isinstance(paper.get("authors"), list) else ""
        lines.extend(
            [
                f"### {paper.get('rank', '')}. {paper.get('title', '')}",
                "",
                f"- 年份/期刊：{paper.get('year', '')} / {paper.get('venue', '')}",
                f"- 作者：{authors}",
                f"- 来源：{paper.get('source', '')}",
                f"- 检索源：{paper.get('retrieval_source', '')}",
                f"- URL：{paper.get('url', '')}",
                f"- 相关性评分：{paper.get('relevance_score', '')}",
                f"- 支撑类型：{paper.get('support_type', '')}",
                f"- 用途：{paper.get('usage_zh', '')}",
                f"- 证据质量：{paper.get('evidence_quality', '')}",
                f"- 证据质量理由：{paper.get('evidence_quality_reason_zh', '')}",
                f"- 中文摘要压缩：{paper.get('summary_zh', '')}",
                f"- 主要贡献：{paper.get('key_contribution_zh', '')}",
                f"- 局限性：{paper.get('limitations_zh', '')}",
                "",
            ]
        )
    return "\n".join(lines)


def retrieve_literature_bundle(
    prompt: str,
    max_papers: int = 20,
    allow_network: bool = True,
    ollama_url: str = "http://localhost:11434",
    ollama_model_name: str = "",
) -> dict[str, Any]:
    plan_warning = ""
    screen_warning = ""
    try:
        plan = plan_literature_queries(prompt, max_papers, allow_network, ollama_url, ollama_model_name)
    except Exception as exc:
        plan_warning = str(exc)
        plan = {"keywords": [], "queries": [prompt], "rationale_zh": "Ollama 检索规划不可用，使用原始任务作为检索词。", "_ollama_model": "unavailable"}
    candidates, search_errors, source_counts = initial_literature_search(plan, prompt, max_papers=max(max_papers * 3, max_papers), allow_network=allow_network)
    if not candidates:
        detail = "; ".join(search_errors[:5]) if search_errors else "arXiv/Crossref/Semantic Scholar 未返回候选文献。"
        raise RuntimeError(f"联网文献检索没有返回可用结果，已停止。详情：{detail}")
    try:
        papers, screen_payload = llm_screen_papers(prompt, candidates, max_papers, ollama_url, ollama_model_name)
    except Exception as exc:
        screen_warning = str(exc)
        papers = deterministic_screen_online_papers(prompt, candidates, max_papers)
        screen_payload = {"overall_assessment_zh": "Ollama 文献筛选不可用，已对联网候选文献使用关键词和引用数进行确定性筛选。", "_ollama_model": "unavailable"}
    report = build_chinese_literature_report(prompt, plan, papers, screen_payload, allow_network)
    return {
        "papers": papers,
        "report_markdown": report,
        "search_plan": plan,
        "target_candidates": candidates,
        "source_paper_selection": screen_payload,
        "online_source_counts": source_counts,
        "candidate_count": len(candidates),
        "requested_max_papers": max_papers,
        "returned_paper_count": len(papers),
        "llm_screening": screen_payload,
        "warnings": {"planning": plan_warning, "screening": screen_warning, "online_search": search_errors},
    }


def retrieve_literature(prompt: str, max_papers: int = 20, allow_network: bool = True) -> list[dict[str, Any]]:
    return retrieve_literature_bundle(prompt, max_papers=max_papers, allow_network=allow_network)["papers"]
