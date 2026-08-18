from __future__ import annotations

from typing import Any

import httpx

from paper_rag.config import Settings
from paper_rag.retrieval import HybridRetriever, SearchResult


class RagService:
    def __init__(self, settings: Settings, retriever: HybridRetriever):
        self.settings = settings
        self.retriever = retriever

    def answer(self, question: str, top_k: int = 8) -> dict[str, Any]:
        sources = self.retriever.search(question, top_k=top_k)
        if not sources:
            return {"answer": "没有检索到足够的论文证据。", "sources": []}
        context = "\n\n".join(self._format_source(i, source) for i, source in enumerate(sources, 1))
        prompt = (
            "你是严谨的科研文献助手。只依据给定论文片段回答；证据不足时明确说明。"
            "每个事实性结论都用[1]这样的编号引用来源，不要虚构 DOI、页码或结论。\n\n"
            f"问题：{question}\n\n论文证据：\n{context}"
        )
        response = httpx.post(
            f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json={
                "model": self.settings.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        answer = payload["choices"][0]["message"]["content"]
        return {"answer": answer, "sources": [source.to_dict() for source in sources]}

    @staticmethod
    def _format_source(index: int, source: SearchResult) -> str:
        pages = ""
        if source.page_start is not None:
            pages = f", pages={source.page_start}"
            if source.page_end and source.page_end != source.page_start:
                pages += f"-{source.page_end}"
        return (
            f"[{index}] title={source.title}; doi={source.doi or 'N/A'}; "
            f"journal={source.journal}; section={source.section_title}{pages}\n{source.content}"
        )
