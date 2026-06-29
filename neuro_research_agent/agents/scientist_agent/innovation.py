from __future__ import annotations

import itertools
import json
import random
import re
from pathlib import Path
from typing import Any

import requests

from neuro_research_agent.agents.scientist_agent.literature import ollama_model, parse_json_object


STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "in", "to", "for", "with", "by", "on", "from", "as", "at",
    "across", "analysis", "analyses", "analyzing", "data", "brain", "neural", "neuroscience", "study",
    "studies", "method", "methods", "theory", "practice", "using", "related", "linked",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", value.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def _compact_papers(papers: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    compact = []
    for paper in papers[:limit]:
        compact.append(
            {
                "title": paper.get("title", ""),
                "year": paper.get("year"),
                "venue": paper.get("venue", ""),
                "keywords": paper.get("keywords", []),
                "finding": str(paper.get("finding") or paper.get("summary_zh") or "")[:900],
                "key_contribution_zh": paper.get("key_contribution_zh", ""),
                "limitations_zh": paper.get("limitations_zh", ""),
                "relevance_score": paper.get("relevance_score", 0),
            }
        )
    return compact


def _compact_paradigms(candidates: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    compact = []
    for item in candidates[:limit]:
        compact.append(
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "keywords": item.get("keywords", []),
                "required_data": item.get("required_data", []),
                "missing_data": item.get("missing_data", []),
                "outputs": item.get("outputs", []),
                "executable": bool(item.get("executable")),
                "prompt_match_score": item.get("prompt_match_score", 0),
                "data_compatibility_score": item.get("data_compatibility_score", 0),
                "selection_score": item.get("selection_score", 0),
            }
        )
    return compact


def _compact_kg_context(kg_context: dict[str, Any] | None, limit: int = 8) -> dict[str, Any]:
    if not isinstance(kg_context, dict) or not kg_context:
        return {}
    feasibility = kg_context.get("local_data_feasibility") if isinstance(kg_context.get("local_data_feasibility"), dict) else {}
    return {
        "available": bool(kg_context.get("available")),
        "mode": kg_context.get("mode", ""),
        "sources": kg_context.get("sources", [])[:limit],
        "matched_hypotheses": kg_context.get("matched_hypotheses", [])[:limit],
        "matched_claims": kg_context.get("matched_claims", [])[:limit],
        "literature_claims": kg_context.get("literature_claims", [])[:limit],
        "region_terms": kg_context.get("region_terms", [])[:limit * 2],
        "roi_hints": kg_context.get("roi_hints", {}),
        "local_data_feasibility": {
            "available_data_types": feasibility.get("available_data_types", []),
            "analysis_routes": feasibility.get("analysis_routes", [])[:limit],
        },
        "idea_generation_guidance": kg_context.get("idea_generation_guidance", []),
    }


def _compact_execution_results(execution_results: list[dict[str, Any]], limit: int = 30) -> list[dict[str, Any]]:
    compact = []
    for item in execution_results[:limit]:
        result_payload: dict[str, Any] = {}
        result_json = item.get("result_json")
        if result_json:
            try:
                path = Path(str(result_json))
                if path.exists():
                    result_payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                result_payload = {}
        compact.append(
            {
                "experiment_id": item.get("experiment_id", ""),
                "innovation_id": item.get("innovation_id", ""),
                "paradigm": item.get("paradigm", ""),
                "status": item.get("status", ""),
                "result_status": item.get("result_status", ""),
                "returncode": item.get("returncode"),
                "elapsed_seconds": item.get("elapsed_seconds"),
                "stdout_tail": str(item.get("stdout", ""))[-1200:],
                "stderr_tail": str(item.get("stderr", ""))[-1200:],
                "result_json": result_json or "",
                "result_payload": result_payload,
            }
        )
    return compact


def _call_ollama_text(base_url: str, configured_model: str, system_prompt: str, user_prompt: str, timeout: int = 120) -> dict[str, Any]:
    model = ollama_model(base_url, configured_model)
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.7, "top_p": 0.95},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = parse_json_object(str(response.json().get("response", "")))
    payload["_ollama_model"] = model
    return payload


def _base_system_prompt() -> str:
    return (
        "You are an Idea Generation Agent for neuroscience research. "
        "Adapt the ideation style of AI-Researcher: read the supplied literature/context, identify research gaps, "
        "generate feasible but nontrivial ideas, and include enough technical detail to guide implementation. "
        "Use a hypothesis-driven workflow: propose multiple concrete experimental candidates, explain the "
        "scientific reasoning for each candidate, expand each candidate into a testable hypothesis, and make it rankable "
        "by pairwise comparison. "
        "Also adapt AI-Scientist-style ideation: propose ideas as structured JSON, explicitly judge novelty against "
        "related work, include experimental plans, and revise ideas after critique. "
        "Return JSON only. Do not use fixed templates. Do not invent unavailable data. "
        "Ground every idea in supplied papers, candidate analysis routes, and available data. "
        "When KG evidence is supplied, use it as structured evidence for claims, gaps, trends, ROI hints, and local-data feasibility. "
        "The innovation point must be a scientific or methodological neuroscience idea, not a workflow-management idea. "
        "Forbidden as innovation points: directory organization, binding outputs to folders, logging, report formatting, "
        "quality-control bookkeeping, or merely saying that an analysis route will be run. "
        "All human-readable result fields must be written in Chinese, including hypotheses, innovation points, "
        "rationales, novelty arguments, methods, experimental plans, risk factors, reflection notes, and update explanations."
    )


def _candidate_user_prompt(
    prompt: str,
    papers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    previous_ideas: list[dict[str, Any]],
    index: int,
    kg_context: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        {
            "task": "Generate one new neuroscience innovation candidate.",
            "research_prompt": prompt,
            "candidate_index": index,
            "papers": _compact_papers(papers),
            "candidate_paradigms": _compact_paradigms(candidates),
            "kg_evidence_and_local_data_feasibility": _compact_kg_context(kg_context),
            "previous_ideas_to_avoid": [
                {
                    "innovation_point": item.get("innovation_point", ""),
                    "hypothesis": item.get("hypothesis", ""),
                    "paradigm_id": item.get("paradigm_id", ""),
                }
                for item in previous_ideas
            ],
            "required_schema": {
                "paradigm_ids": ["one or more candidate paradigm ids"],
                "paradigm_name": "short readable name",
                "hypothesis": "中文：具体、可证伪的神经科学假设",
                "innovation_point": "中文：具体科学/方法创新点；必须说明要检验的机制或指标，不要写目录、流程、运行实验路线或报告生成",
                "rationale": "中文：该创新点由哪些文献空白和数据条件支持",
                "kg_evidence": ["中文：使用到的 KG claim/hypothesis/ROI 证据；没有则写明仅由文献和本地数据支持"],
                "local_data_feasibility_zh": "中文：说明当前本地数据能否检验该 idea，缺什么数据，哪些指标可直接计算",
                "novelty_argument": "中文：为什么不同于已有相关工作",
                "proposed_method": "中文：具体分析或建模方法",
                "experimental_plan": ["中文：使用已有输出的逐步实验/分析计划"],
                "testable_outputs": ["expected output artifacts or metrics"],
                "risk_factors": ["中文：混杂因素、缺失数据限制或解释风险"],
                "supporting_papers": ["paper titles from supplied papers"],
                "expected_result_pattern_zh": "中文：如果假设成立，关键指标应呈现什么模式",
                "alternative_explanation_zh": "中文：如果观察到该模式，还有哪些替代解释",
            },
        },
        ensure_ascii=False,
    )


def _reflection_prompt(
    prompt: str,
    idea: dict[str, Any],
    papers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    kg_context: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        {
            "task": "Critique and improve this neuroscience innovation candidate.",
            "research_prompt": prompt,
            "idea_to_refine": idea,
            "papers": _compact_papers(papers),
            "candidate_paradigms": _compact_paradigms(candidates),
            "kg_evidence_and_local_data_feasibility": _compact_kg_context(kg_context),
            "instructions": [
                "Check whether the idea is genuinely distinct from supplied related work.",
                "Check whether KG evidence supports, contradicts, or leaves a gap for the idea.",
                "Check whether the proposed ROI/edge/metric is feasible with local data.",
                "Make the hypothesis more falsifiable.",
                "Remove claims that require missing data.",
                "Strengthen the experimental plan and risk controls.",
            ],
            "required_schema": {
                "paradigm_ids": ["one or more candidate paradigm ids"],
                "paradigm_name": "short readable name",
                "hypothesis": "中文：具体、可证伪的神经科学假设",
                "innovation_point": "中文：具体科学/方法创新点；必须说明要检验的机制或指标，不要写目录、流程、运行实验路线或报告生成",
                "rationale": "中文：该创新点由哪些文献空白和数据条件支持",
                "kg_evidence": ["中文：使用到的 KG claim/hypothesis/ROI 证据；没有则写明仅由文献和本地数据支持"],
                "local_data_feasibility_zh": "中文：说明当前本地数据能否检验该 idea，缺什么数据，哪些指标可直接计算",
                "novelty_argument": "中文：为什么不同于已有相关工作",
                "proposed_method": "中文：具体分析或建模方法",
                "experimental_plan": ["中文：使用已有输出的逐步实验/分析计划"],
                "testable_outputs": ["expected output artifacts or metrics"],
                "risk_factors": ["中文：混杂因素、缺失数据限制或解释风险"],
                "supporting_papers": ["paper titles from supplied papers"],
                "expected_result_pattern_zh": "中文：如果假设成立，关键指标应呈现什么模式",
                "alternative_explanation_zh": "中文：如果观察到该模式，还有哪些替代解释",
                "reflection_notes": "中文：本轮自我反思修改了什么、为什么这样修改",
            },
        },
        ensure_ascii=False,
    )


def _pairwise_prompt(
    prompt: str,
    idea_a: dict[str, Any],
    idea_b: dict[str, Any],
    papers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    kg_context: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        {
            "task": "Compare two neuroscience innovation candidates. Choose the stronger idea.",
            "research_prompt": prompt,
            "idea_a": idea_a,
            "idea_b": idea_b,
            "papers": _compact_papers(papers),
            "candidate_paradigms": _compact_paradigms(candidates),
            "kg_evidence_and_local_data_feasibility": _compact_kg_context(kg_context),
            "criteria": {
                "novelty": "distinct from supplied related work and not a direct baseline",
                "feasibility": "testable with available candidate paradigms and data outputs",
                "kg_grounding": "supported by KG claims/hypotheses or clearly targets a KG gap/contradiction",
                "scientific_value": "would clarify a mechanism or meaningful neuroscience question",
                "risk_control": "explicitly handles confounds, missing modalities, and interpretation limits",
            },
            "required_schema": {
                "winner": "A or B",
                "loser": "A or B",
                "reason_zh": "用中文说明胜出原因",
                "dimension_preference": {
                    "novelty": "A/B/tie",
                    "feasibility": "A/B/tie",
                    "kg_grounding": "A/B/tie",
                    "scientific_value": "A/B/tie",
                    "risk_control": "A/B/tie",
                },
                "concise_comparison_zh": "用中文概括这次 pairwise 比较",
            },
        },
        ensure_ascii=False,
    )


def _experimental_update_prompt(prompt: str, innovations: list[dict[str, Any]], execution_results: list[dict[str, Any]]) -> str:
    required_ids = [str(item.get("id", "")) for item in innovations if item.get("id")]
    return json.dumps(
        {
            "task": "Update neuroscience innovation points after experimental/computational execution results.",
            "research_prompt": prompt,
            "current_innovations": [
                {
                    "id": item.get("id", ""),
                    "paradigm_id": item.get("paradigm_id", ""),
                    "hypothesis": item.get("hypothesis", ""),
                    "innovation_point": item.get("innovation_point", ""),
                    "experimental_plan": item.get("experimental_plan", []),
                    "risk_factors": item.get("risk_factors", []),
                }
                for item in innovations
            ],
            "execution_results": _compact_execution_results(execution_results),
            "instructions": [
                "Use only the supplied execution results. Do not invent significant effects.",
                f"Return one update for every innovation id exactly as written: {required_ids}.",
                "Do not renumber ids. For example, innovation_01 must not be returned as innovation_1.",
                "For each innovation, say whether the result supports, weakens, or does not yet test the hypothesis.",
                "Revise the innovation point and next experiment when results justify a change.",
                "Write the explanation in Chinese for readability.",
            ],
            "required_schema": {
                "updated_innovations": [
                    {
                        "id": "existing innovation id",
                        "result_interpretation_zh": "中文解释实验/计算结果如何影响该创新点",
                        "updated_hypothesis_zh": "更新后的中文假设",
                        "updated_innovation_point_zh": "更新后的中文创新点",
                        "next_experiment_zh": "下一步实验或分析建议",
                        "confidence": "low/medium/high",
                    }
                ],
                "overall_update_zh": "中文总结实验结果对创新点集合的整体影响",
            },
        },
        ensure_ascii=False,
    )


def _canonical_innovation_id(value: Any) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"innovation[_-]?(\d+)", text, flags=re.I)
    if match:
        return f"innovation_{int(match.group(1)):02d}"
    return text


def _linked_execution_records(innovation: dict[str, Any], execution_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    innovation_id = _canonical_innovation_id(innovation.get("id", ""))
    paradigm_ids = [part for part in str(innovation.get("paradigm_id", "")).split("+") if part]
    linked: list[dict[str, Any]] = []
    for record in execution_results:
        record_innovation = _canonical_innovation_id(record.get("innovation_id") or record.get("experiment_id"))
        record_paradigm = str(record.get("paradigm", ""))
        if record_innovation == innovation_id and (not paradigm_ids or record_paradigm in paradigm_ids):
            linked.append(record)
    if linked:
        return linked
    for record in execution_results:
        if str(record.get("paradigm", "")) in paradigm_ids:
            linked.append(record)
    return linked


def _execution_payload(record: dict[str, Any]) -> dict[str, Any]:
    result_json = record.get("result_json")
    if not result_json:
        return {}
    try:
        path = Path(str(result_json))
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _result_metric_summary(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"texts": [], "region_labels": []}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        paradigm = str(payload.get("paradigm", ""))
        metric_summary = payload.get("metric_summary") if isinstance(payload.get("metric_summary"), dict) else {}
        outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
        edge_summary = outputs.get("connectome_edge_summary") if isinstance(outputs.get("connectome_edge_summary"), dict) else {}
        labels = payload.get("region_labels") if isinstance(payload.get("region_labels"), list) else []
        summary["region_labels"].extend([str(label) for label in labels])
        if paradigm == "resting_state_functional_connectivity":
            mean_r = metric_summary.get("mean_r", edge_summary.get("mean_r"))
            mean_abs_r = metric_summary.get("mean_abs_r")
            max_abs_r = metric_summary.get("max_abs_r")
            pos = edge_summary.get("positive_edge_count")
            neg = edge_summary.get("negative_edge_count")
            edge_count = metric_summary.get("edge_count")
            parts = []
            if mean_r is not None:
                parts.append(f"平均相关 r={float(mean_r):.4f}")
            if mean_abs_r is not None:
                parts.append(f"平均绝对相关 |r|={float(mean_abs_r):.4f}")
            if max_abs_r is not None:
                parts.append(f"最大绝对相关={float(max_abs_r):.4f}")
            if pos is not None and neg is not None:
                parts.append(f"正相关边 {pos} 条、负相关边 {neg} 条")
            if edge_count is not None:
                parts.append(f"总边数 {edge_count} 条")
            if parts:
                summary["texts"].append("静息态功能连接结果：" + "，".join(parts) + "。")
        elif paradigm == "dynamic_functional_connectivity":
            for key, value in (payload.get("dynamic_summary") or payload.get("metric_summary") or {}).items():
                if isinstance(value, (int, float)):
                    summary["texts"].append(f"动态功能连接指标 {key}={float(value):.4f}。")
        elif paradigm == "graph_theory_connectomics":
            graph = payload.get("graph_metrics") if isinstance(payload.get("graph_metrics"), dict) else {}
            if graph:
                brief = [f"{key}={float(value):.4f}" for key, value in graph.items() if isinstance(value, (int, float))]
                if brief:
                    summary["texts"].append("图论指标：" + "，".join(brief[:6]) + "。")
        elif paradigm:
            status = payload.get("status", "")
            summary["texts"].append(f"{paradigm} 执行状态为 {status}。")
    labels_lower = " ".join(summary["region_labels"]).lower()
    summary["has_cerebellum"] = any(token in labels_lower for token in ["cerebell", "小脑"])
    summary["has_metric_text"] = bool(summary["texts"])
    return summary


def _metric_driven_revision(innovation: dict[str, Any], completed: list[dict[str, Any]], execution_results: list[dict[str, Any]]) -> dict[str, str]:
    payloads = [_execution_payload(record) for record in completed]
    metric_summary = _result_metric_summary(payloads)
    original_point = str(innovation.get("innovation_point", ""))
    original_hypothesis = str(innovation.get("hypothesis", ""))
    metric_text = " ".join(metric_summary.get("texts", [])) or "关联 result.json 未提供足够的量化指标。"
    mentions_cerebellum = any(token in (original_point + original_hypothesis).lower() for token in ["cerebell", "小脑"])
    if mentions_cerebellum and not metric_summary.get("has_cerebellum"):
        updated_point = (
            "将原“跨网络-小脑连接偏置指数”修正为“皮层跨区连接偏置指数（小脑项待补充检验）”："
            "当前 aparcaseg ROI 未包含小脑节点，因此本轮只能比较额叶、顶叶、颞叶等皮层 ROI 的 Fisher-Z 连接强度、"
            "正负边比例和 top-edge 空间分布；小脑相关偏置需在后续加入小脑 ROI/atlas 后再检验。"
        )
        updated_hypothesis = (
            "在当前被试已处理 fMRI 中，可先检验皮层 ROI 之间是否存在跨区连接偏置；"
            "由于本轮 ROI 标签未覆盖小脑，原假设中的“小脑相关连接”暂不能被当前结果支持或否定。"
        )
        interpretation = (
            f"关联实验已完成，但结果对原创新点形成了约束：{metric_text}"
            "同时，region_labels 未发现小脑 ROI，因此原创新点中的“小脑连接”部分当前不可检验，"
            "应从本轮结论中移除或标记为待补充。"
        )
        next_experiment = "补充包含小脑分区的 atlas 或显式小脑 ROI 后重新提取时间序列，再计算皮层-小脑边、皮层内边和跨皮层边的 Fisher-Z 偏置指数。"
    else:
        paradigms = ", ".join([str(record.get("paradigm", "")) for record in completed if record.get("paradigm")])
        updated_point = (
            f"将原创新点修正为结果约束版：围绕已完成的 {paradigms}，"
            f"使用实际量化指标（{metric_text}）界定可检验的连接表型，"
            "避免仅停留在概念性机制描述。"
        )
        updated_hypothesis = (
            f"{original_hypothesis} 当前应被表述为单被试、当前 ROI/实验路线条件下的可检验假设；"
            "是否具有群体稳定性需要更多被试和敏感性分析。"
        )
        interpretation = f"关联实验已完成，并产生了可用于修正创新点的量化摘要：{metric_text}"
        next_experiment = "围绕上述指标进行阈值敏感性分析、ROI atlas 敏感性分析，并扩展到更多被试验证稳定性。"
    return {
        "result_interpretation_zh": interpretation,
        "updated_hypothesis_zh": updated_hypothesis,
        "updated_innovation_point_zh": updated_point,
        "next_experiment_zh": next_experiment,
    }


def _fallback_execution_update(innovation: dict[str, Any], execution_results: list[dict[str, Any]]) -> dict[str, Any]:
    linked = _linked_execution_records(innovation, execution_results)
    completed = [
        record
        for record in linked
        if record.get("status") == "completed" and record.get("result_status") in {"", None, "completed"} and record.get("returncode") in {0, None}
    ]
    failed = [
        record
        for record in linked
        if record.get("status") in {"failed", "timeout", "not_executed", "not_executable"} or record.get("returncode") not in {0, None}
    ]
    completed_paradigms = [str(record.get("paradigm", "")) for record in completed if record.get("paradigm")]
    failed_paradigms = [str(record.get("paradigm", "")) for record in failed if record.get("paradigm")]
    if completed:
        result_paths = [str(record.get("result_json", "")) for record in completed if record.get("result_json")]
        revision = _metric_driven_revision(innovation, completed, execution_results)
        interpretation = revision["result_interpretation_zh"]
        if result_paths:
            interpretation += f" 结果文件：{'; '.join(result_paths[:3])}。"
        confidence = "medium"
    elif failed:
        interpretation = (
            f"关联实验未成功完成：{', '.join(failed_paradigms)}。"
            "当前不能用实验结果支持或削弱该创新点，反向更新应优先修正可执行性、数据依赖和失败条件。"
        )
        confidence = "low"
    else:
        interpretation = "未找到与该创新点直接关联的执行结果，因此该创新点尚未被当前实验检验。"
        confidence = "low"
    return {
        "id": innovation.get("id", ""),
        "result_interpretation_zh": interpretation,
        "updated_hypothesis_zh": revision.get("updated_hypothesis_zh", innovation.get("hypothesis", "")) if completed else innovation.get("hypothesis", ""),
        "updated_innovation_point_zh": revision.get("updated_innovation_point_zh", innovation.get("innovation_point", "")) if completed else innovation.get("innovation_point", ""),
        "next_experiment_zh": revision.get("next_experiment_zh", "基于 result.json 中的核心指标、QC 图和 connectome 图进行人工核查；若指标稳定，再扩展到更多被试或做敏感性分析。") if completed else "基于 result.json 中的核心指标、QC 图和 connectome 图进行人工核查；若指标稳定，再扩展到更多被试或做敏感性分析。",
        "confidence": confidence,
        "linked_execution_count": len(linked),
        "completed_paradigms": completed_paradigms,
        "failed_paradigms": failed_paradigms,
    }


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []


def _reflection_summary_zh(reflection: dict[str, Any]) -> str:
    notes = str(reflection.get("reflection_notes", "")).strip()
    if notes:
        return notes
    parts = []
    if reflection.get("hypothesis"):
        parts.append(f"将假设收敛为：{reflection.get('hypothesis')}")
    if reflection.get("novelty_argument"):
        parts.append(f"新颖性检查：{reflection.get('novelty_argument')}")
    if reflection.get("risk_factors"):
        parts.append(f"风险控制：{'；'.join(_normalize_list(reflection.get('risk_factors')))}")
    return "；".join(parts) or "完成一轮自我反思，但模型未返回单独的 reflection_notes。"


def _looks_like_workflow_template(text: str) -> bool:
    lowered = text.lower()
    forbidden = [
        "组织成一个独立创新实验",
        "绑定到同一个实验目录",
        "实验目录",
        "目录",
        "result.json",
        "执行日志",
        "运行该实验路线",
        "run the candidate paradigm",
        "reporting a descriptive result",
        "workflow",
    ]
    return any(token in lowered for token in forbidden)


def _kg_route_feasibility(valid_ids: list[str], kg_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(kg_context, dict):
        return []
    feasibility = kg_context.get("local_data_feasibility") if isinstance(kg_context.get("local_data_feasibility"), dict) else {}
    rows = feasibility.get("analysis_routes", []) if isinstance(feasibility.get("analysis_routes"), list) else []
    valid = set(valid_ids)
    return [row for row in rows if str(row.get("analysis_route_id", "")) in valid]


def _coerce_idea(
    index: int,
    raw: dict[str, Any],
    prompt: str,
    candidates: list[dict[str, Any]],
    kg_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_by_id = {item.get("id", ""): item for item in candidates}
    paradigm_ids = _normalize_list(raw.get("paradigm_ids") or raw.get("paradigm_id"))
    valid_ids = [pid for pid in paradigm_ids if pid in candidate_by_id]
    if not valid_ids and candidates:
        valid_ids = [str(candidates[0].get("id", ""))]
    if _looks_like_workflow_template(str(raw.get("innovation_point", ""))) and valid_ids:
        repaired = _mechanistic_blueprint(candidate_by_id.get(valid_ids[0], candidates[0]), prompt, index)
        raw = {
            **raw,
            "hypothesis": repaired["hypothesis"],
            "innovation_point": repaired["innovation"],
            "proposed_method": repaired["method"],
            "expected_result_pattern_zh": repaired["expected"],
            "alternative_explanation_zh": repaired["alternative"],
            "_reflection_process_zh": [
                *(_normalize_list(raw.get("_reflection_process_zh"))),
                "检测到原始创新点偏向工程流程模板，已自动修复为机制假设型创新点。",
            ],
        }
    paradigm_names = [str(candidate_by_id[pid].get("name", pid)) for pid in valid_ids if pid in candidate_by_id]
    testable_outputs = _normalize_list(raw.get("testable_outputs"))
    if not testable_outputs:
        for pid in valid_ids:
            testable_outputs.extend(_normalize_list(candidate_by_id.get(pid, {}).get("outputs", [])))
    prompt_terms = _tokens(prompt)
    paradigm_terms = _tokens(" ".join(valid_ids + paradigm_names))
    kg_evidence = _normalize_list(raw.get("kg_evidence"))
    if not kg_evidence and isinstance(kg_context, dict):
        for claim in (kg_context.get("matched_hypotheses", []) + kg_context.get("matched_claims", []) + kg_context.get("literature_claims", []))[:3]:
            if isinstance(claim, dict):
                label = claim.get("raw_sentence") or claim.get("finding") or claim.get("target_name") or claim.get("title") or claim.get("id")
                if label:
                    kg_evidence.append(str(label)[:260])
    route_feasibility = _kg_route_feasibility(valid_ids, kg_context)
    local_data_feasibility_zh = str(raw.get("local_data_feasibility_zh", "")).strip()
    if not local_data_feasibility_zh and route_feasibility:
        executable = [row for row in route_feasibility if row.get("executable")]
        missing = [row for row in route_feasibility if row.get("missing_data")]
        if executable:
            local_data_feasibility_zh = "当前本地数据可支持至少一条绑定实验路线，可直接生成并运行对应指标。"
        elif missing:
            local_data_feasibility_zh = "当前本地数据存在缺口：" + "；".join(
                f"{row.get('analysis_route_id')}: 缺少 {', '.join(row.get('missing_data', []))}" for row in missing[:3]
            )
    return {
        "id": f"innovation_{index:02d}",
        "paradigm_id": "+".join(valid_ids),
        "paradigm_name": raw.get("paradigm_name") or " + ".join(paradigm_names),
        "hypothesis": str(raw.get("hypothesis", "")).strip(),
        "innovation_point": str(raw.get("innovation_point", "")).strip(),
        "rationale": str(raw.get("rationale", "")).strip(),
        "novelty_argument": str(raw.get("novelty_argument", "")).strip(),
        "proposed_method": str(raw.get("proposed_method", "")).strip(),
        "experimental_plan": _normalize_list(raw.get("experimental_plan")),
        "risk_factors": _normalize_list(raw.get("risk_factors")),
        "shared_prompt_terms": sorted(prompt_terms & paradigm_terms),
        "supporting_papers": _normalize_list(raw.get("supporting_papers"))[:4],
        "kg_evidence": kg_evidence[:8],
        "kg_region_terms": list((kg_context or {}).get("region_terms", []))[:20] if isinstance(kg_context, dict) else [],
        "kg_roi_hints": (kg_context or {}).get("roi_hints", {}) if isinstance(kg_context, dict) else {},
        "local_data_feasibility_zh": local_data_feasibility_zh,
        "kg_route_feasibility": route_feasibility,
        "testable_outputs": sorted(set(testable_outputs)),
        "expected_result_pattern_zh": str(raw.get("expected_result_pattern_zh", "")).strip(),
        "alternative_explanation_zh": str(raw.get("alternative_explanation_zh", "")).strip(),
        "generation_method": "ai_researcher_ai_scientist_llm",
        "score_dimensions": {
            "novelty": "LLM novelty check against supplied literature and candidate ideas.",
            "feasibility": "Compatibility with discovered data and executable paradigms.",
            "scientific_value": "Mechanistic neuroscience value and interpretability.",
            "risk": "Confounds, missing data, and overclaiming risks.",
        },
        "中文详细说明": {
            "创新点": str(raw.get("innovation_point", "")).strip(),
            "科学假设": str(raw.get("hypothesis", "")).strip(),
            "提出依据": str(raw.get("rationale", "")).strip(),
            "KG证据": kg_evidence[:8],
            "本地数据可行性": local_data_feasibility_zh,
            "新颖性说明": str(raw.get("novelty_argument", "")).strip(),
            "实验或分析方案": _normalize_list(raw.get("experimental_plan")),
            "风险控制": _normalize_list(raw.get("risk_factors")),
            "预期结果模式": str(raw.get("expected_result_pattern_zh", "")).strip(),
            "替代解释": str(raw.get("alternative_explanation_zh", "")).strip(),
            "自我反思过程": _normalize_list(raw.get("_reflection_process_zh")),
            "pairwise_tournament排序过程": [],
            "实验结果反向更新": "尚未执行实验/计算分析，等待 execution_results 后更新。",
        },
    }


def _round_robin_pairs(n_items: int, max_pairs: int = 300) -> list[tuple[int, int]]:
    pairs = list(itertools.combinations(range(1, n_items + 1), 2))
    if len(pairs) <= max_pairs:
        return pairs
    rng = random.Random(0)
    return sorted(rng.sample(pairs, max_pairs))


def _winner_from_payload(payload: dict[str, Any], left_index: int, right_index: int) -> tuple[int, int] | None:
    winner = str(payload.get("winner", "")).strip().upper()
    loser = str(payload.get("loser", "")).strip().upper()
    if winner == "A" and loser in {"B", ""}:
        return left_index, right_index
    if winner == "B" and loser in {"A", ""}:
        return right_index, left_index
    return None


def _heuristic_pairwise_winner(idea_a: dict[str, Any], idea_b: dict[str, Any], left_index: int, right_index: int) -> tuple[int, int]:
    def score(idea: dict[str, Any]) -> int:
        return (
            len(_normalize_list(idea.get("supporting_papers"))) * 3
            + len(_normalize_list(idea.get("testable_outputs"))) * 2
            + len(_normalize_list(idea.get("experimental_plan")))
            + len(_normalize_list(idea.get("risk_factors")))
            + len(str(idea.get("novelty_argument", ""))) // 80
        )

    return (left_index, right_index) if score(idea_a) >= score(idea_b) else (right_index, left_index)


def _estimate_btl_strengths(n_items: int, games: list[tuple[int, int]], alpha: float = 0.1, iterations: int = 200) -> list[float]:
    if n_items <= 0:
        return []
    if not games:
        return [1.0 / n_items for _ in range(n_items)]
    try:
        import choix

        params = choix.ilsr_pairwise(n_items, [(winner - 1, loser - 1) for winner, loser in games], alpha=alpha)
        exp_params = [float(pow(2.718281828459045, value)) for value in params]
        scale = sum(exp_params) or 1.0
        return [value / scale for value in exp_params]
    except Exception:
        pass
    wins = [alpha for _ in range(n_items)]
    pair_counts = [[0.0 for _ in range(n_items)] for _ in range(n_items)]
    for winner, loser in games:
        if 1 <= winner <= n_items and 1 <= loser <= n_items and winner != loser:
            wins[winner - 1] += 1.0
            pair_counts[winner - 1][loser - 1] += 1.0
            pair_counts[loser - 1][winner - 1] += 1.0
    strengths = [1.0 for _ in range(n_items)]
    for _ in range(iterations):
        updated = strengths[:]
        for i in range(n_items):
            denom = 0.0
            for j in range(n_items):
                if i == j or pair_counts[i][j] == 0:
                    continue
                denom += pair_counts[i][j] / max(strengths[i] + strengths[j], 1e-9)
            updated[i] = wins[i] / max(denom + alpha, 1e-9)
        scale = sum(updated) or 1.0
        strengths = [max(value / scale, 1e-9) for value in updated]
    return strengths


def _run_pairwise_tournament(
    prompt: str,
    raw_ideas: list[dict[str, Any]],
    papers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    ollama_url: str,
    ollama_model_name: str,
    kg_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pairs = _round_robin_pairs(len(raw_ideas))
    comparisons = []
    games: list[tuple[int, int]] = []
    for pair_index, (left_index, right_index) in enumerate(pairs, start=1):
        idea_a = raw_ideas[left_index - 1]
        idea_b = raw_ideas[right_index - 1]
        try:
            payload = _call_ollama_text(
                ollama_url,
                ollama_model_name,
                _base_system_prompt(),
                _pairwise_prompt(prompt, idea_a, idea_b, papers, candidates, kg_context),
            )
            winner_loser = _winner_from_payload(payload, left_index, right_index)
            fallback_used = False
            if winner_loser is None:
                winner_loser = _heuristic_pairwise_winner(idea_a, idea_b, left_index, right_index)
                fallback_used = True
        except Exception as exc:
            payload = {
                "reason_zh": f"LLM pairwise 比较失败，使用结构化兜底比较：{type(exc).__name__}: {exc}",
                "dimension_preference": {},
                "concise_comparison_zh": "根据文献支撑数、可检验输出、实验计划完整度和风险控制完整度进行兜底比较。",
            }
            winner_loser = _heuristic_pairwise_winner(idea_a, idea_b, left_index, right_index)
            fallback_used = True
        winner, loser = winner_loser
        games.append((winner, loser))
        comparisons.append(
            {
                "pair_index": pair_index,
                "idea_a_index": left_index,
                "idea_b_index": right_index,
                "winner_index": winner,
                "loser_index": loser,
                "winner_id": f"innovation_{winner:02d}",
                "loser_id": f"innovation_{loser:02d}",
                "reason_zh": str(payload.get("reason_zh", "")),
                "dimension_preference": payload.get("dimension_preference", {}),
                "concise_comparison_zh": str(payload.get("concise_comparison_zh", "")),
                "fallback_used": fallback_used,
            }
        )
    strengths = _estimate_btl_strengths(len(raw_ideas), games)
    win_counts = {idx: 0 for idx in range(1, len(raw_ideas) + 1)}
    loss_counts = {idx: 0 for idx in range(1, len(raw_ideas) + 1)}
    for winner, loser in games:
        win_counts[winner] += 1
        loss_counts[loser] += 1
    ranking = [
        {
            "source_index": idx,
            "idea_id": f"innovation_{idx:02d}",
            "strength_score": strengths[idx - 1],
            "wins": win_counts[idx],
            "losses": loss_counts[idx],
            "排序说明": f"该 idea 在 pairwise tournament 中 {win_counts[idx]} 胜 {loss_counts[idx]} 负，BTL 强度分为 {strengths[idx - 1]:.4f}。",
        }
        for idx in range(1, len(raw_ideas) + 1)
    ]
    ranking.sort(key=lambda item: (item["strength_score"], item["wins"], -item["losses"]), reverse=True)
    for rank, item in enumerate(ranking, start=1):
        item["rank"] = rank
    return {
        "method": "pairwise_tournament_btl",
        "方法中文说明": "每次只让模型比较两个创新点，输出胜者和中文理由；全部胜负关系再用 Bradley-Terry-Luce 风格的强度估计转换成总排序。LLM 比较失败时使用结构化兜底比较。",
        "pairs": pairs,
        "comparisons": comparisons,
        "games": games,
        "ranking": ranking,
    }


def _mechanistic_blueprint(candidate: dict[str, Any], prompt: str, index: int) -> dict[str, Any]:
    paradigm_id = str(candidate.get("id", ""))
    name = str(candidate.get("name", paradigm_id))
    blueprints = {
        "resting_state_functional_connectivity": {
            "hypothesis": "目标被试的静息态功能连接中，默认网络、感觉运动网络和小脑相关 ROI 之间的连接强度会呈现可量化的不均衡模式；这种不均衡可作为单被试功能网络表型，而不是只报告平均相关矩阵。",
            "innovation": "提出“跨网络-小脑连接偏置指数”：同时比较网络内连接、跨网络连接和小脑相关连接的 Fisher-Z 强度，用一个方向性指标刻画单被试功能连接偏离模式。",
            "method": "从 ROI 时间序列计算相关矩阵和 Fisher-Z 矩阵，按空间坐标近似划分前后、左右和小脑/非小脑区域，计算网络内均值、跨网络均值、连接强度偏置和 top edges 的 3D connectome。",
            "expected": "如果假设成立，top edges 不会均匀分布，而会集中在特定跨网络或小脑相关边；偏置指数相对全矩阵平均绝对连接明显升高。",
            "alternative": "该模式也可能来自头动残留、配准误差、ROI 划分粗糙或单个 session 时间序列长度不足。",
        },
        "dynamic_functional_connectivity": {
            "hypothesis": "目标被试的功能连接不是静态稳定的，而是在扫描过程中出现若干高连接和低连接窗口；窗口间连接矩阵变化幅度可以反映状态切换特征。",
            "innovation": "提出“单被试动态连接不稳定性曲线”：用滑窗 FC 的均值强度、矩阵距离和 top-edge 重排率刻画状态转移，而不是只给一个全程平均连接矩阵。",
            "method": "对 clean BOLD 做滑动窗口相关分析，计算每个窗口的 mean_abs_r、相邻窗口矩阵距离和平均动态 FC 的 3D connectome，并标记高变异窗口。",
            "expected": "如果假设成立，相邻窗口距离会呈现峰值，且高变异窗口的 top edges 与低变异窗口不同。",
            "alternative": "动态变化可能由生理噪声、残余运动、睡眠深度变化或窗口长度选择造成。",
        },
        "graph_theory_connectomics": {
            "hypothesis": "功能连接图的全局效率和局部模块化之间存在单被试层面的权衡，提示网络整合与分离的平衡状态。",
            "innovation": "提出“效率-模块化失衡画像”：在多个连接阈值下同时追踪节点度、全局效率和模块化趋势，用阈值稳定性而非单阈值图指标支持解释。",
            "method": "从 Fisher-Z 矩阵构建不同密度阈值的图，计算边密度、节点度分布、效率近似指标和 hub 稳定性。",
            "expected": "如果假设成立，核心 hub 在多个阈值下稳定出现，但效率和模块化指标随阈值呈系统性变化。",
            "alternative": "图指标对 ROI 数量、阈值、负相关处理和时间序列长度高度敏感。",
        },
        "alff_falff_frequency": {
            "hypothesis": "目标被试的低频 BOLD 振幅在部分 ROI 或体素簇中增强，可能对应局部自发活动强度差异。",
            "innovation": "提出“低频振幅-连接耦合检验”：将 ALFF/fALFF 摘要与 ROI 连接强度排序联合解释，区分局部振幅增强和网络连接增强。",
            "method": "计算低频段功率摘要，提取高 ALFF 区域对应的时间序列连接强度，比较其与全脑平均连接的差异。",
            "expected": "如果假设成立，高 ALFF 区域同时显示更高的连接参与度或特定连接边增强。",
            "alternative": "低频振幅可能受血管、运动、滤波策略和空间平滑影响。",
        },
        "surface_based_analysis": {
            "hypothesis": "皮层表面空间中的 BOLD 信号变化比体素空间更能保留皮层拓扑特征，可能揭示体积分析中被平滑掩盖的局部差异。",
            "innovation": "提出“体积-表面一致性检查”：比较 surface BOLD 与 volume BOLD 的可用性和信号摘要，识别哪些结论依赖空间表达方式。",
            "method": "读取 fsaverage/fsnative surface 文件，统计左右半球信号覆盖和时间维度，与 volume clean BOLD 的 ROI 指标进行一致性对照。",
            "expected": "如果假设成立，表面数据会在特定半球或空间表达中显示更清晰的信号差异。",
            "alternative": "表面配准质量、皮层重建失败或空间标准化误差可能造成差异。",
        },
        "sleep_stage_analysis": {
            "hypothesis": "睡眠/清醒片段之间的功能连接拓扑不同，清醒期更可能表现为跨网络连接增强，睡眠期更可能表现为局部或低频同步增强。",
            "innovation": "提出“睡眠-清醒连接重排指数”：直接比较 W/S 分段 clean BOLD 的 top edges、平均连接强度和 3D connectome 空间分布。",
            "method": "读取 segment clean_data 中的 W_*/S_* 文件，分别计算连接矩阵和 3D connectome，比较片段间 top-edge Jaccard 距离和 mean_abs_r。",
            "expected": "如果假设成立，睡眠与清醒片段的 top edges 重叠率较低，并且某一阶段出现更高的局部连接。",
            "alternative": "阶段标签误差、片段长度不均衡和清洗策略差异可能解释观察到的差异。",
        },
        "behavioral_computational_modeling": {
            "hypothesis": "如果后续补充行为指标，单被试功能连接偏置可以作为计算模型中的潜变量，解释反应速度、准确率或状态评分的个体内波动。",
            "innovation": "提出“连接表型驱动的行为潜变量模型”：把 FC 偏置、动态不稳定性和图指标作为潜变量候选，而不是直接把行为分数与全脑平均连接做相关。",
            "method": "在当前无行为数据时先生成可导出的连接特征表；一旦行为数据可用，用层级回归或漂移扩散模型检验连接特征对行为参数的解释增益。",
            "expected": "如果假设成立，连接偏置特征会解释超出 session 或运动协变量之外的行为变异。",
            "alternative": "行为关联可能由疲劳、任务难度、药物状态或未建模的生理噪声驱动。",
        },
    }
    default = {
        "hypothesis": f"{name} 可以从当前数据中提取一个可量化的神经表型，但必须明确该表型对应的机制解释和失败条件。",
        "innovation": f"提出基于 {name} 输出的单被试机制检验：把主要指标、预期方向和替代解释同时纳入创新假设，而不是只报告实验路线结果。",
        "method": f"运行 {paradigm_id} 对应分析，提取主要输出指标，并与文献提示的机制方向进行对照。",
        "expected": "如果假设成立，主要指标应表现出方向一致的偏离模式，而不是随机或不可解释的变化。",
        "alternative": "该结果可能由数据缺失、预处理差异、样本量不足或实验路线与当前数据不匹配造成。",
    }
    item = blueprints.get(paradigm_id, default)
    item["title"] = f"机制候选 {index}: {item['innovation'].split('：', 1)[0]}"
    return item


def _fallback_data_grounded_idea(
    prompt: str,
    papers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    idea_count: int = 8,
    kg_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Data-grounded fallback that still returns multiple scientific Chinese experiment ideas."""
    if not candidates:
        return []
    paper_titles = [paper.get("title", "") for paper in papers[:4] if paper.get("title")]
    selected = candidates[: max(1, min(idea_count, len(candidates)))]
    points = []
    for index, candidate in enumerate(selected, start=1):
        missing = _normalize_list(candidate.get("missing_data"))
        outputs = _normalize_list(candidate.get("outputs"))
        executable_note = "当前数据满足该实验路线的基础输入要求" if not missing else f"当前缺失 {', '.join(missing)}，因此该实验主要作为后续补数或替代分析计划"
        blueprint = _mechanistic_blueprint(candidate, prompt, index)
        kg_claims = []
        if isinstance(kg_context, dict):
            kg_claims = [
                str(item.get("raw_sentence") or item.get("finding") or item.get("target_name") or item.get("title") or item.get("id", ""))[:260]
                for item in (kg_context.get("matched_hypotheses", []) + kg_context.get("matched_claims", []) + kg_context.get("literature_claims", []))[:4]
                if isinstance(item, dict)
            ]
        kg_note = f"KG/文献结构化证据提示：{'；'.join(kg_claims[:2])}。" if kg_claims else "当前未发现可用外部 KG snapshot，使用检索文献与本地数据可行性作为轻量 KG evidence。"
        raw = {
            "paradigm_ids": [candidate.get("id", "")],
            "paradigm_name": candidate.get("name", ""),
            "hypothesis": blueprint["hypothesis"],
            "innovation_point": blueprint["innovation"],
            "rationale": f"数据驱动候选生成：先把候选实验路线视为可检验 assay，再为其写出机制假设、预期结果和替代解释。该实验路线候选得分为 {candidate.get('selection_score', 0)}；{executable_note}。{kg_note} 相关文献用于约束解释边界：{'; '.join(paper_titles[:2]) if paper_titles else '当前文献摘要有限'}。",
            "kg_evidence": kg_claims,
            "local_data_feasibility_zh": executable_note,
            "novelty_argument": "该创新点不是简单运行既有实验路线，而是提出可证伪的指标组合或机制指数，并要求用预期结果模式和替代解释约束结论。",
            "proposed_method": blueprint["method"],
            "experimental_plan": [
                "读取已处理 fMRI derivatives、QC 结果和可用 session。",
                f"执行 {candidate.get('id', '')} 的可执行 py 实验代码，提取可量化指标。",
                "检查指标是否符合预期结果模式，并记录关键图形或矩阵证据。",
                "如果执行失败或指标不支持假设，依据失败原因、替代解释和数据缺失情况反向修正创新点。",
            ],
            "testable_outputs": outputs,
            "risk_factors": missing or ["单被试结果不能直接推广到群体结论", "功能连接结果依赖 ROI 提取、配准质量和时间序列长度"],
            "supporting_papers": paper_titles,
            "expected_result_pattern_zh": blueprint["expected"],
            "alternative_explanation_zh": blueprint["alternative"],
            "_reflection_process_zh": [
                "LLM 原始创新点生成失败后，系统按 assay-hypothesis 思路：为每个候选实验路线生成具体机制假设和预期结果。",
                "自我反思时删除工程流程类表述，只保留可检验神经机制、指标组合、替代解释和失败条件。",
            ],
        }
        point = _coerce_idea(index, raw, prompt, candidates, kg_context)
        point["generation_method"] = "data_grounded_multi_fallback"
        point["pairwise_tournament_review"] = {
            "rank": index,
            "排序说明": "LLM 候选生成失败，兜底创新点按候选实验路线 selection_score 顺序排列；未进行真实 pairwise tournament。",
        }
        point["中文详细说明"]["pairwise_tournament排序过程"] = [
            "LLM 候选生成阶段失败，无法形成多条 LLM 原始 idea 的 pairwise tournament；本条按候选实验路线排序生成。",
        ]
        points.append(point)
    return points


def derive_innovation_points(
    prompt: str,
    papers: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    ollama_url: str = "http://localhost:11434",
    ollama_model_name: str = "",
    idea_count: int = 8,
    reflection_rounds: int = 1,
    kg_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate innovation points with an AI-Researcher/AI-Scientist-style LLM ideation loop."""
    if not candidates:
        return []
    idea_count = max(8, min(12, max(idea_count, len(candidates[:8]))))
    raw_ideas: list[dict[str, Any]] = []
    generation_records: list[dict[str, Any]] = []
    try:
        for index in range(1, max(1, idea_count) + 1):
            payload = _call_ollama_text(
                ollama_url,
                ollama_model_name,
                _base_system_prompt(),
                _candidate_user_prompt(prompt, papers, candidates, raw_ideas, index, kg_context),
            )
            idea = {k: v for k, v in payload.items() if not k.startswith("_")}
            original_idea = dict(idea)
            reflection_process_zh: list[str] = []
            reflections: list[dict[str, Any]] = []
            for round_index in range(1, max(0, reflection_rounds) + 1):
                refined = _call_ollama_text(
                    ollama_url,
                    ollama_model_name,
                    _base_system_prompt(),
                    _reflection_prompt(prompt, idea, papers, candidates, kg_context),
                )
                idea = {k: v for k, v in refined.items() if not k.startswith("_")}
                summary = _reflection_summary_zh(idea)
                reflection_process_zh.append(f"第 {round_index} 轮自我反思：{summary}")
                reflections.append(idea)
            idea["_reflection_process_zh"] = reflection_process_zh
            raw_ideas.append(idea)
            generation_records.append(
                {
                    "source_index": index,
                    "original_idea": original_idea,
                    "reflections": reflections,
                    "final_idea": idea,
                    "自我反思过程": reflection_process_zh,
                }
            )
    except Exception as exc:
        fallback = _fallback_data_grounded_idea(prompt, papers, candidates, idea_count, kg_context)
        for item in fallback:
            item["generation_warning"] = f"LLM ideation unavailable: {type(exc).__name__}: {exc}"
        return fallback

    tournament = _run_pairwise_tournament(prompt, raw_ideas, papers, candidates, ollama_url, ollama_model_name, kg_context)
    rank_by_source = {int(item["source_index"]): item for item in tournament.get("ranking", [])}
    points = []
    ranked_sources = [int(item["source_index"]) for item in tournament.get("ranking", [])]
    if not ranked_sources:
        ranked_sources = list(range(1, len(raw_ideas) + 1))
    for output_index, source_index in enumerate(ranked_sources[: max(1, min(idea_count, len(raw_ideas)))], start=1):
        point = _coerce_idea(output_index, raw_ideas[source_index - 1], prompt, candidates, kg_context)
        ranking_info = rank_by_source.get(source_index, {})
        point["source_idea_index"] = source_index
        point["pairwise_tournament_review"] = ranking_info
        point["pairwise_tournament"] = {
            "method": tournament.get("method"),
            "方法中文说明": tournament.get("方法中文说明"),
            "ranking": tournament.get("ranking", []),
            "comparisons": tournament.get("comparisons", []),
        }
        related_comparisons = [
            item
            for item in tournament.get("comparisons", [])
            if item.get("idea_a_index") == source_index or item.get("idea_b_index") == source_index
        ]
        point["中文详细说明"]["pairwise_tournament排序过程"] = [
            f"总排序第 {ranking_info.get('rank', output_index)} 名：{ranking_info.get('排序说明', '')}",
            *[
                (
                    f"比较 {item.get('pair_index')}: idea_{item.get('idea_a_index'):02d} vs idea_{item.get('idea_b_index'):02d}，"
                    f"胜者 {item.get('winner_id')}；原因：{item.get('reason_zh') or item.get('concise_comparison_zh')}"
                )
                for item in related_comparisons
            ],
        ]
        point["generation_trace"] = generation_records[source_index - 1]
        points.append(point)
    return points


def update_innovations_from_execution(
    prompt: str,
    innovations: list[dict[str, Any]],
    execution_results: list[dict[str, Any]],
    ollama_url: str = "http://localhost:11434",
    ollama_model_name: str = "",
) -> dict[str, Any]:
    """Update innovation points after experiments/computational analyses finish."""
    if not innovations:
        return {
            "updated_innovations": [],
            "overall_update_zh": "没有可更新的创新点。",
            "method": "no_innovations",
        }
    if not execution_results:
        updates = []
        for item in innovations:
            update = {
                "id": item.get("id", ""),
                "result_interpretation_zh": "当前没有实验或计算执行结果，因此该创新点尚不能被结果支持或削弱。",
                "updated_hypothesis_zh": item.get("hypothesis", ""),
                "updated_innovation_point_zh": item.get("innovation_point", ""),
                "next_experiment_zh": "先执行该创新点关联的分析脚本，并检查 result.json 中的关键指标。",
                "confidence": "low",
            }
            item.setdefault("中文详细说明", {})["实验结果反向更新"] = update["result_interpretation_zh"]
            item["experimental_update"] = update
            updates.append(update)
        return {
            "updated_innovations": updates,
            "overall_update_zh": "未发现 execution_results，创新点保持原始版本，仅记录下一步需要执行分析。",
            "method": "no_execution_results",
        }

    try:
        payload = _call_ollama_text(
            ollama_url,
            ollama_model_name,
            _base_system_prompt(),
            _experimental_update_prompt(prompt, innovations, execution_results),
        )
        payload["method"] = "llm_experimental_feedback_update"
    except Exception as exc:
        updates = []
        for item in innovations:
            update = _fallback_execution_update(item, execution_results)
            item.setdefault("中文详细说明", {})["实验结果反向更新"] = update.get("result_interpretation_zh", "")
            item["experimental_update"] = update
            updates.append(update)
        return {
            "updated_innovations": updates,
            "overall_update_zh": f"LLM 反向更新失败，已使用执行状态生成保守中文更新：{type(exc).__name__}: {exc}",
            "method": "execution_status_fallback_update",
        }

    updates_by_id = {
        _canonical_innovation_id(item.get("id", "")): item
        for item in payload.get("updated_innovations", [])
        if isinstance(item, dict)
    }
    final_updates = []
    for item in innovations:
        update = updates_by_id.get(_canonical_innovation_id(item.get("id", "")))
        if not update:
            update = _fallback_execution_update(item, execution_results)
            update["llm_update_missing"] = True
        update["id"] = item.get("id", update.get("id", ""))
        item.setdefault("中文详细说明", {})["实验结果反向更新"] = update.get("result_interpretation_zh", "")
        item["experimental_update"] = update
        final_updates.append(update)
    payload["updated_innovations"] = final_updates
    payload["updated_innovation_count"] = len(final_updates)
    if not payload.get("overall_update_zh"):
        payload["overall_update_zh"] = "已根据真实执行结果为每个创新点生成反向更新；LLM 缺失或 ID 不规范的条目已由本地执行结果兜底补齐。"
    return payload


def build_innovation_process_document(
    prompt: str,
    innovations: list[dict[str, Any]],
    execution_update: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# 创新点生成过程",
        "",
        f"## 用户问题",
        "",
        prompt,
        "",
        "## 方法概述",
        "",
        "1. LLM 根据用户问题、文献和候选实验路线生成多条候选创新点。",
        "2. 每条候选创新点生成后进行自我反思，检查新颖性、可证伪性、缺失数据依赖和风险控制。",
        "3. 自我反思后不再做统一评审，而是采用 pairwise tournament：每次比较两个 idea，记录胜者、败者和中文理由。",
        "4. 将所有胜负关系输入 Bradley-Terry-Luce 排序；优先使用 `choix.ilsr_pairwise`，失败时使用本地 BTL 排序。",
        "5. 实验/计算执行完成后，根据 execution_results 反向更新每个创新点；如果没有执行结果，也会记录“尚未被结果检验”的更新状态。",
        "",
    ]
    for item in innovations:
        detail = item.get("中文详细说明", {})
        lines.extend(
            [
                f"## {item.get('id', '')}：{item.get('paradigm_name', '')}",
                "",
                f"- 创新点：{detail.get('创新点') or item.get('innovation_point', '')}",
                f"- 科学假设：{detail.get('科学假设') or item.get('hypothesis', '')}",
                f"- 提出依据：{detail.get('提出依据') or item.get('rationale', '')}",
                f"- 新颖性说明：{detail.get('新颖性说明') or item.get('novelty_argument', '')}",
                "",
                "### 自我反思过程",
                "",
            ]
        )
        reflections = detail.get("自我反思过程") or []
        if reflections:
            lines.extend([f"- {text}" for text in reflections])
        else:
            lines.append("- 未记录自我反思过程。")
        lines.extend(["", "### Pairwise Tournament 排序过程", ""])
        tournament_steps = detail.get("pairwise_tournament排序过程") or []
        if tournament_steps:
            lines.extend([f"- {text}" for text in tournament_steps])
        else:
            lines.append("- 未记录 pairwise tournament 过程。")
        lines.extend(
            [
                "",
                "### 实验结果反向更新",
                "",
                f"- {detail.get('实验结果反向更新', '尚未更新。')}",
                "",
            ]
        )
    if execution_update:
        lines.extend(
            [
                "## 实验结果整体反向更新",
                "",
                execution_update.get("overall_update_zh", ""),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
