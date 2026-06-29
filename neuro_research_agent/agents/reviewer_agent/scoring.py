from __future__ import annotations

from typing import Any


def score_literature_support(paradigm_id: str, papers: list[dict[str, Any]]) -> int:
    score = 0
    for paper in papers:
        text = " ".join([paper.get("title", ""), paper.get("finding", ""), " ".join(paper.get("keywords", [])), paper.get("topic", "")]).lower()
        for token in paradigm_id.split("_"):
            if token and token in text:
                score += 3
    return min(20, max(5, score))


def evaluate_paradigms(
    candidates: list[dict[str, Any]],
    papers: list[dict[str, Any]],
    code_map: dict[str, list[dict[str, Any]]],
    innovations: list[dict[str, Any]],
    execution_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    innovation_ids = {item.get("paradigm_id", "") for item in innovations}
    execution_map: dict[str, dict[str, Any]] = {}
    for execution in execution_results:
        paradigm_id = str(execution.get("paradigm", ""))
        current = execution_map.get(paradigm_id)
        if current is None or (execution.get("status") == "completed" and current.get("status") != "completed"):
            execution_map[paradigm_id] = execution
    for item in candidates:
        literature_score = score_literature_support(item["id"], papers)
        data_score = int(item.get("data_compatibility_score", 0))
        code_score = min(15, 5 + len(code_map.get(item["id"], [])) * 3)
        execution = execution_map.get(item["id"], {})
        execution_status = execution.get("status", "not_run")
        if execution_status == "completed" and execution.get("returncode") == 0:
            feasibility_score = 20
        elif item.get("executable"):
            feasibility_score = 16
        else:
            feasibility_score = max(5, 20 - len(item.get("missing_data", [])) * 5)
        novelty_score = min(15, 8 + int(item.get("prompt_match_score", 0)) + (3 if item["id"] in innovation_ids else 0))
        score_total = int(literature_score + data_score + code_score + feasibility_score + novelty_score)
        rows.append(
            {
                "id": item["id"],
                "name": item["name"],
                "executable": bool(item["executable"]),
                "execution_status": execution_status,
                "execution_result": execution.get("result_json", ""),
                "missing_data": item.get("missing_data", []),
                "template": item.get("template", ""),
                "literature_score": literature_score,
                "data_score": data_score,
                "code_score": code_score,
                "feasibility_score": feasibility_score,
                "novelty_score": novelty_score,
                "score_total": min(100, score_total),
            }
        )
    rows.sort(key=lambda row: row["score_total"], reverse=True)
    return rows


def evaluate_innovations(
    innovations: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    execution_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evaluation_map = {item.get("id"): item for item in evaluations}
    execution_by_pair = {(item.get("innovation_id"), item.get("paradigm")): item for item in execution_results if item.get("innovation_id")}
    execution_by_paradigm: dict[str, dict[str, Any]] = {}
    for execution in execution_results:
        paradigm_id = str(execution.get("paradigm", ""))
        current = execution_by_paradigm.get(paradigm_id)
        if current is None or (execution.get("status") == "completed" and current.get("status") != "completed"):
            execution_by_paradigm[paradigm_id] = execution
    rows: list[dict[str, Any]] = []
    for item in innovations:
        paradigm_ids = [part for part in str(item.get("paradigm_id", "")).split("+") if part]
        linked_scores = [evaluation_map[pid].get("score_total", 0) for pid in paradigm_ids if pid in evaluation_map]
        linked_executions = [
            execution_by_pair.get((item.get("id"), pid), execution_by_paradigm.get(pid, {})).get("status", "not_run")
            for pid in paradigm_ids
        ]
        support_count = len(item.get("supporting_papers", []))
        novelty = min(25, 12 + len(paradigm_ids) * 4 + len(item.get("shared_prompt_terms", [])))
        feasibility = int(sum(linked_scores) / len(linked_scores) * 0.25) if linked_scores else 8
        scientific_value = min(25, 10 + support_count * 3 + len(item.get("testable_outputs", [])))
        risk_penalty = 0
        if any(status in {"not_executable", "not_executed", "failed", "timeout"} for status in linked_executions):
            risk_penalty += 5
        if not linked_scores:
            risk_penalty += 4
        risk_control = max(5, 25 - risk_penalty)
        total = min(100, novelty + feasibility + scientific_value + risk_control)
        rows.append(
            {
                "id": item.get("id", ""),
                "paradigm_id": item.get("paradigm_id", ""),
                "paradigm_name": item.get("paradigm_name", ""),
                "innovation_point": item.get("innovation_point", ""),
                "hypothesis": item.get("hypothesis", ""),
                "novelty_score": novelty,
                "feasibility_score": feasibility,
                "scientific_value_score": scientific_value,
                "risk_control_score": risk_control,
                "score_total": int(total),
                "linked_execution_status": linked_executions,
                "supporting_paper_count": support_count,
            }
        )
    rows.sort(key=lambda row: row["score_total"], reverse=True)
    return rows
