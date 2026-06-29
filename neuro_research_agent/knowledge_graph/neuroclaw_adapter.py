from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


DEFAULT_NEUROCLAW_ROOT = Path("/home/qlp/Agent_skills/NeuroClaw-main")


REGION_TO_AAL_HINTS: dict[str, list[str]] = {
    "anterior cingulate": ["Cingulum_Ant_L", "Cingulum_Ant_R"],
    "cingulate": ["Cingulum_Ant_L", "Cingulum_Ant_R", "Cingulum_Mid_L", "Cingulum_Mid_R", "Cingulum_Post_L", "Cingulum_Post_R"],
    "insula": ["Insula_L", "Insula_R"],
    "caudate": ["Caudate_L", "Caudate_R"],
    "angular gyrus": ["Angular_L", "Angular_R"],
    "cuneus": ["Cuneus_L", "Cuneus_R"],
    "precuneus": ["Precuneus_L", "Precuneus_R"],
    "temporal pole": ["Temporal_Pole_Sup_L", "Temporal_Pole_Sup_R", "Temporal_Pole_Mid_L", "Temporal_Pole_Mid_R"],
    "occipital": ["Occipital_Sup_L", "Occipital_Sup_R", "Occipital_Mid_L", "Occipital_Mid_R", "Occipital_Inf_L", "Occipital_Inf_R"],
    "thalamus": ["Thalamus_L", "Thalamus_R"],
    "hypothalamus": ["Thalamus_L", "Thalamus_R"],
    "hippocampus": ["Hippocampus_L", "Hippocampus_R"],
    "parahippocampal": ["ParaHippocampal_L", "ParaHippocampal_R"],
    "frontoparietal": ["Frontal_Mid_L", "Frontal_Mid_R", "Parietal_Inf_L", "Parietal_Inf_R"],
    "frontal": ["Frontal_Sup_L", "Frontal_Sup_R", "Frontal_Mid_L", "Frontal_Mid_R", "Frontal_Inf_Oper_L", "Frontal_Inf_Oper_R"],
    "parietal": ["Parietal_Sup_L", "Parietal_Sup_R", "Parietal_Inf_L", "Parietal_Inf_R"],
    "temporal": ["Temporal_Sup_L", "Temporal_Sup_R", "Temporal_Mid_L", "Temporal_Mid_R", "Temporal_Inf_L", "Temporal_Inf_R"],
    "fusiform": ["Fusiform_L", "Fusiform_R"],
    "olfactory": ["Olfactory_L", "Olfactory_R"],
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", value.lower())
        if len(token) > 2
    }


def _text_similarity(query_tokens: set[str], value: Any) -> int:
    if not query_tokens:
        return 0
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value or "")
    return len(query_tokens & _tokens(text))


def _safe_load_json(path: Path) -> Any | None:
    try:
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _candidate_kg_files(neuroclaw_root: Path) -> dict[str, list[str]]:
    explicit = os.environ.get("NEURO_RESEARCH_AGENT_KG_PATH", "").strip()
    hypotheses = os.environ.get("NEURO_RESEARCH_AGENT_KG_HYPOTHESES", "").strip()
    graph = os.environ.get("NEURO_RESEARCH_AGENT_KG_GRAPH", "").strip()
    candidates = {
        "explicit": [explicit] if explicit else [],
        "hypotheses": [hypotheses] if hypotheses else [],
        "graph": [graph] if graph else [],
    }
    for rel in (
        "neurooracle/data/quick/hypotheses_imaging_hcp.json",
        "neurooracle/data/hypotheses.json",
        "neurooracle/data/full_snapshot_v2/hypotheses.json",
        "materials/huggingface/NeuroOracle/hypotheses.json",
    ):
        candidates["hypotheses"].append(str(neuroclaw_root / rel))
    for rel in (
        "neurooracle/data/full_snapshot_v2/knowledge_graph.json",
        "neurooracle/data/knowledge_graph.json",
        "materials/huggingface/NeuroOracle/knowledge_graph.json",
    ):
        candidates["graph"].append(str(neuroclaw_root / rel))
    return candidates


def _load_first_json(paths: list[str]) -> tuple[Path | None, Any | None]:
    for raw in paths:
        path = Path(raw).expanduser()
        payload = _safe_load_json(path)
        if payload is not None:
            return path, payload
    return None, None


def _iter_hypotheses(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("hypotheses", "items", "data", "results"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
        if payload.get("id") or payload.get("metadata"):
            return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _iter_claim_like_records(payload: Any, limit: int = 5000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in ("claims", "nodes", "edges", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                records.extend(item for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                records.extend(item for item in value.values() if isinstance(item, dict))
        if not records and (payload.get("subject") or payload.get("predicate") or payload.get("source_id")):
            records.append(payload)
    elif isinstance(payload, list):
        records.extend(item for item in payload if isinstance(item, dict))
    return records[:limit]


def _rank_records(records: list[dict[str, Any]], prompt: str, limit: int) -> list[dict[str, Any]]:
    query_tokens = _tokens(prompt)
    ranked = []
    for record in records:
        score = _text_similarity(query_tokens, record)
        if score <= 0 and query_tokens:
            continue
        confidence = record.get("confidence_score", record.get("composite_score", record.get("confidence", 0)))
        try:
            confidence_value = float(confidence or 0)
        except Exception:
            confidence_value = 0.0
        ranked.append((score, confidence_value, record))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [_compact_record(record) for _, _, record in ranked[:limit]]


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    return {
        "id": record.get("id", record.get("hypothesis_id", record.get("claim_id", ""))),
        "subject": record.get("subject", record.get("source_name", meta.get("input_region", ""))),
        "predicate": record.get("predicate", record.get("relation_type", "")),
        "object": record.get("object", record.get("target_name", "")),
        "target_name": record.get("target_name", ""),
        "source_name": record.get("source_name", ""),
        "confidence_score": record.get("confidence_score", record.get("confidence", "")),
        "composite_score": record.get("composite_score", ""),
        "raw_sentence": record.get("raw_sentence", record.get("description", "")),
        "metadata": {
            "input_modality": meta.get("input_modality", ""),
            "input_feature": meta.get("input_feature", ""),
            "input_region": meta.get("input_region", ""),
            "methodology": record.get("methodology", meta.get("methodology", "")),
        },
    }


def _extract_region_terms(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower() if isinstance(value, (dict, list)) else str(value or "").lower()
    regions = []
    for region in REGION_TO_AAL_HINTS:
        if region in text:
            regions.append(region)
    return sorted(set(regions))


def _map_regions_to_roi_hints(regions: list[str]) -> dict[str, list[str]]:
    return {region: REGION_TO_AAL_HINTS.get(region, []) for region in regions if REGION_TO_AAL_HINTS.get(region)}


def _literature_claims_from_papers(papers: list[dict[str, Any]], prompt: str, limit: int = 12) -> list[dict[str, Any]]:
    query_tokens = _tokens(prompt)
    ranked = []
    for paper in papers:
        text = " ".join(
            str(paper.get(key, ""))
            for key in ("title", "finding", "summary_zh", "key_contribution_zh", "limitations_zh", "topic")
        )
        score = _text_similarity(query_tokens, text)
        if score <= 0 and query_tokens:
            continue
        ranked.append((score, paper))
    ranked.sort(key=lambda item: item[0], reverse=True)
    claims = []
    for _, paper in ranked[:limit]:
        claims.append(
            {
                "title": paper.get("title", ""),
                "year": paper.get("year", ""),
                "finding": str(paper.get("finding") or paper.get("summary_zh") or "")[:800],
                "key_contribution_zh": paper.get("key_contribution_zh", ""),
                "limitations_zh": paper.get("limitations_zh", ""),
                "source": "retrieved_literature",
            }
        )
    return claims


def _route_feasibility(candidates: list[dict[str, Any]], data_types: set[str]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates[:12]:
        required = set(str(item) for item in candidate.get("required_data", []))
        missing = sorted(required - data_types)
        rows.append(
            {
                "analysis_route_id": candidate.get("id", ""),
                "analysis_route_name": candidate.get("name", ""),
                "required_data": sorted(required),
                "missing_data": missing,
                "executable": not missing,
                "selection_score": candidate.get("selection_score", 0),
                "testable_outputs": candidate.get("outputs", []),
            }
        )
    return rows


def build_kg_context(
    prompt: str,
    papers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    data_types: set[str],
    neuroclaw_root: Path | None = None,
) -> dict[str, Any]:
    """Build KG evidence for idea generation.

    The adapter is intentionally optional: it consumes NeuroClaw/NeuroOracle JSON
    snapshots when available, and otherwise falls back to a lightweight KG-style
    evidence bundle derived from retrieved literature and local data feasibility.
    """
    root = neuroclaw_root or Path(os.environ.get("NEUROCLAW_ROOT", str(DEFAULT_NEUROCLAW_ROOT))).expanduser()
    paths = _candidate_kg_files(root)
    hypothesis_path, hypothesis_payload = _load_first_json(paths["explicit"] + paths["hypotheses"])
    graph_path, graph_payload = _load_first_json(paths["graph"])

    raw_hypotheses = _iter_hypotheses(hypothesis_payload)
    raw_graph_records = _iter_claim_like_records(graph_payload)
    matched_hypotheses = _rank_records(raw_hypotheses, prompt, limit=20)
    matched_graph_claims = _rank_records(raw_graph_records, prompt, limit=20)

    fallback_literature_claims = _literature_claims_from_papers(papers, prompt)
    region_terms = sorted(
        set(
            _extract_region_terms(matched_hypotheses)
            + _extract_region_terms(matched_graph_claims)
            + _extract_region_terms(fallback_literature_claims)
            + _extract_region_terms(prompt)
        )
    )
    roi_hints = _map_regions_to_roi_hints(region_terms)
    feasibility = _route_feasibility(candidates, data_types)

    evidence_count = len(matched_hypotheses) + len(matched_graph_claims) + len(fallback_literature_claims)
    sources = []
    if hypothesis_path:
        sources.append({"kind": "neurooracle_hypotheses", "path": str(hypothesis_path), "matched_count": len(matched_hypotheses)})
    if graph_path:
        sources.append({"kind": "neurooracle_graph", "path": str(graph_path), "matched_count": len(matched_graph_claims)})
    if fallback_literature_claims:
        sources.append({"kind": "retrieved_literature_claims", "matched_count": len(fallback_literature_claims)})
    return {
        "available": evidence_count > 0 or bool(feasibility),
        "mode": "neurooracle_json" if hypothesis_path or graph_path else "literature_and_data_fallback",
        "neuroclaw_root": str(root),
        "sources": sources,
        "matched_hypotheses": matched_hypotheses,
        "matched_claims": matched_graph_claims,
        "literature_claims": fallback_literature_claims,
        "region_terms": region_terms,
        "roi_hints": roi_hints,
        "local_data_feasibility": {
            "available_data_types": sorted(data_types),
            "analysis_routes": feasibility,
        },
        "idea_generation_guidance": [
            "优先生成同时被文献 claim、KG hypothesis 和本地数据可行性支持的 idea。",
            "如果 KG 指向脑区或网络，尽量把 idea 落到 ROI、ROI pair、FC edge 或可计算指标。",
            "如果 KG evidence 存在但本地数据缺失，保留为下一轮 idea，并明确缺失数据与补数路径。",
            "避免只复述 KG claim；每个 idea 必须转化为当前数据可执行或可判定不可执行的实验计划。",
        ],
    }
