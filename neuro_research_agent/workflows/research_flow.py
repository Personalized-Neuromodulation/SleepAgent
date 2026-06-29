from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from neuro_research_agent.agents import AnalystAgent, CoderAgent, PlannerAgent, ReviewerAgent, ScientistAgent
from neuro_research_agent.core.io import write_json, write_text
from neuro_research_agent.core.types import ResearchContext
from neuro_research_agent.knowledge_graph import build_kg_context


def progress_log(stage: str, agent: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{stage}] agent={agent} | {message}", flush=True)


def _compact_markdown_value(value: Any, depth: int = 0, max_items: int = 8) -> Any:
    if depth >= 3:
        text = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else str(value)
        return text[:600] + ("..." if len(text) > 600 else "")
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                compact["..."] = f"{len(value) - max_items} more keys"
                break
            compact[str(key)] = _compact_markdown_value(item, depth + 1, max_items)
        return compact
    if isinstance(value, list):
        compact_list = [_compact_markdown_value(item, depth + 1, max_items) for item in value[:max_items]]
        if len(value) > max_items:
            compact_list.append(f"... {len(value) - max_items} more items")
        return compact_list
    return value


def _markdown_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        text = str(value)
    else:
        text = json.dumps(_compact_markdown_value(value), ensure_ascii=False, indent=2, default=str)
    return text.replace("\n", " ").strip()


def payload_to_markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [f"# {title}", ""]
    summary_keys = [
        "index",
        "name",
        "elapsed_seconds",
        "mode",
        "status",
        "paper_count",
        "candidate_count",
        "innovation_count",
        "result_count",
        "source_count",
        "matched_hypothesis_count",
        "matched_claim_count",
        "literature_claim_count",
    ]
    summary_rows = [(key, payload.get(key)) for key in summary_keys if key in payload]
    if summary_rows:
        lines.extend(["## Summary", "", "| Field | Value |", "| --- | --- |"])
        for key, value in summary_rows:
            lines.append(f"| `{key}` | {_markdown_scalar(value)} |")
        lines.append("")

    for key, value in payload.items():
        if key in {item[0] for item in summary_rows}:
            continue
        lines.extend([f"## {key}", ""])
        compact = _compact_markdown_value(value)
        if isinstance(compact, list):
            for item in compact:
                if isinstance(item, dict):
                    lines.append("```json")
                    lines.append(json.dumps(item, ensure_ascii=False, indent=2, default=str))
                    lines.append("```")
                else:
                    lines.append(f"- {_markdown_scalar(item)}")
            lines.append("")
        elif isinstance(compact, dict):
            lines.append("```json")
            lines.append(json.dumps(compact, ensure_ascii=False, indent=2, default=str))
            lines.append("```")
            lines.append("")
        else:
            lines.append(_markdown_scalar(compact))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_payload_markdown(path: Path, title: str, payload: dict[str, Any]) -> None:
    write_text(path, payload_to_markdown(title, payload))


def kg_context_to_markdown(kg_context: dict[str, Any]) -> str:
    lines = [
        "# KG Evidence Context",
        "",
        f"- Mode: `{kg_context.get('mode', '')}`",
        f"- NeuroClaw root: `{kg_context.get('neuroclaw_root', '')}`",
        f"- Sources: {len(kg_context.get('sources', []))}",
        f"- Matched hypotheses: {len(kg_context.get('matched_hypotheses', []))}",
        f"- Matched claims: {len(kg_context.get('matched_claims', []))}",
        f"- Literature claims: {len(kg_context.get('literature_claims', []))}",
        "",
    ]
    if kg_context.get("sources"):
        lines.extend(["## Sources", ""])
        for source in kg_context.get("sources", []):
            lines.append(f"- `{source.get('kind', '')}` {source.get('path', '')} matched={source.get('matched_count', '')}")
        lines.append("")
    if kg_context.get("region_terms"):
        lines.extend(["## Region Terms", "", ", ".join(str(item) for item in kg_context.get("region_terms", [])), ""])
    if kg_context.get("roi_hints"):
        lines.extend(["## ROI Hints", ""])
        for region, rois in kg_context.get("roi_hints", {}).items():
            lines.append(f"- **{region}**: {', '.join(str(roi) for roi in rois)}")
        lines.append("")
    for heading, key in (
        ("Matched Hypotheses", "matched_hypotheses"),
        ("Matched Claims", "matched_claims"),
        ("Literature Claims", "literature_claims"),
    ):
        values = kg_context.get(key, [])
        if values:
            lines.extend([f"## {heading}", ""])
            for item in values[:20]:
                label = item.get("raw_sentence") or item.get("finding") or item.get("target_name") or item.get("title") or item.get("id", "")
                meta = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
                lines.append(f"- {label}")
                if meta:
                    details = ", ".join(f"{k}={v}" for k, v in meta.items() if v)
                    if details:
                        lines.append(f"  - metadata: {details}")
            lines.append("")
    feasibility = kg_context.get("local_data_feasibility", {})
    if isinstance(feasibility, dict):
        lines.extend(["## Local Data Feasibility", ""])
        lines.append(f"- Available data types: {', '.join(feasibility.get('available_data_types', []))}")
        lines.extend(["", "| Analysis Route | Executable | Missing Data | Outputs |", "| --- | --- | --- | --- |"])
        for route in feasibility.get("analysis_routes", []):
            lines.append(
                f"| `{route.get('analysis_route_id', '')}` | {route.get('executable', '')} | "
                f"{', '.join(route.get('missing_data', []))} | {', '.join(route.get('testable_outputs', []))} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


class StepRecorder:
    def __init__(self, root: Path):
        self.root = root / "steps"
        self.steps: list[dict[str, Any]] = []
        self.index = 0
        self.root.mkdir(parents=True, exist_ok=True)

    def record(self, name: str, payload: dict[str, Any], started: float) -> Path:
        self.index += 1
        elapsed = int(time.time() - started)
        path = self.root / f"{self.index:02d}_{name}.json"
        md_path = self.root / f"{self.index:02d}_{name}.md"
        step = {
            "index": self.index,
            "name": name,
            "elapsed_seconds": elapsed,
            **payload,
        }
        write_json(path, step)
        write_payload_markdown(md_path, f"Step {self.index:02d}: {name}", step)
        self.steps.append(
            {
                "index": self.index,
                "name": name,
                "path": str(path),
                "markdown": str(md_path),
                "elapsed_seconds": elapsed,
            }
        )
        write_json(self.root / "manifest.json", self.steps)
        self.write_manifest_markdown()
        return path

    def write_manifest_markdown(self) -> None:
        lines = ["# Step Manifest", "", "| # | Step | Seconds | Markdown |", "| ---: | --- | ---: | --- |"]
        for step in self.steps:
            lines.append(
                f"| {step['index']} | `{step['name']}` | {step['elapsed_seconds']} | {step.get('markdown', '')} |"
            )
        write_text(self.root / "manifest.md", "\n".join(lines))


def safe_path_id(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def bound_paradigm_ids(innovation: dict[str, Any], candidate_by_id: dict[str, dict[str, Any]]) -> list[str]:
    raw = str(innovation.get("paradigm_id", "") or innovation.get("paradigm_ids", ""))
    parts = [part.strip() for part in re.split(r"[+,;，、\s]+", raw) if part.strip()]
    valid = []
    for part in parts:
        if part in candidate_by_id and part not in valid:
            valid.append(part)
    if not valid and candidate_by_id:
        valid.append(next(iter(candidate_by_id)))
    return valid


def build_literature_context(innovation: dict[str, Any], papers: list[dict[str, Any]]) -> dict[str, Any]:
    supporting = set(str(title) for title in innovation.get("supporting_papers", []))
    selected = []
    for paper in papers:
        if not supporting or paper.get("title", "") in supporting:
            selected.append(
                {
                    "title": paper.get("title", ""),
                    "year": paper.get("year", ""),
                    "url": paper.get("url", ""),
                    "venue": paper.get("venue", ""),
                    "key_contribution_zh": paper.get("key_contribution_zh", ""),
                    "limitations_zh": paper.get("limitations_zh", ""),
                    "finding": paper.get("finding", ""),
                }
            )
        if len(selected) >= 8:
            break
    return {
        "agent_reference": "scientist_agent",
        "说明": "为该创新点保留直接相关文献、贡献、限制和可写作依据。",
        "innovation_id": innovation.get("id", ""),
        "innovation_point_zh": innovation.get("innovation_point", ""),
        "hypothesis_zh": innovation.get("hypothesis", ""),
        "kg_evidence": innovation.get("kg_evidence", []),
        "kg_region_terms": innovation.get("kg_region_terms", []),
        "kg_roi_hints": innovation.get("kg_roi_hints", {}),
        "local_data_feasibility_zh": innovation.get("local_data_feasibility_zh", ""),
        "supporting_papers": selected,
    }


def build_experiment_plan(innovation: dict[str, Any], bound_ids: list[str], generated_records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "agent_reference": "planner_agent+scientist_agent+coder_agent+reviewer_agent+analyst_agent",
        "说明": "围绕一个创新点组织研究假设、实验代码、执行结果和反向修正。",
        "innovation_id": innovation.get("id", ""),
        "hypothesis_zh": innovation.get("hypothesis", ""),
        "innovation_point_zh": innovation.get("innovation_point", ""),
        "expected_result_pattern_zh": innovation.get("expected_result_pattern_zh", ""),
        "alternative_explanation_zh": innovation.get("alternative_explanation_zh", ""),
        "kg_evidence": innovation.get("kg_evidence", []),
        "kg_region_terms": innovation.get("kg_region_terms", []),
        "kg_roi_hints": innovation.get("kg_roi_hints", {}),
        "local_data_feasibility_zh": innovation.get("local_data_feasibility_zh", ""),
        "kg_route_feasibility": innovation.get("kg_route_feasibility", []),
        "bound_paradigm_ids": bound_ids,
        "experimental_plan": innovation.get("experimental_plan", []),
        "risk_factors": innovation.get("risk_factors", []),
        "generated_scripts": generated_records,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def build_paradigm_details(
    candidates: list[dict[str, Any]],
    papers: list[dict[str, Any]],
    innovations: list[dict[str, Any]],
    code_map: dict[str, Any],
    generated_code: list[dict[str, Any]],
    execution_results: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    generated_by_paradigm: dict[str, list[dict[str, Any]]] = {}
    for item in generated_code:
        generated_by_paradigm.setdefault(str(item.get("paradigm", "")), []).append(item)
    execution_by_paradigm: dict[str, list[dict[str, Any]]] = {}
    for item in execution_results:
        execution_by_paradigm.setdefault(str(item.get("paradigm", "")), []).append(item)
    evaluation_map = {item.get("id"): item for item in evaluations}
    details = []
    for candidate in candidates:
        paradigm_id = candidate["id"]
        generated_items = generated_by_paradigm.get(paradigm_id, [])
        execution_items = execution_by_paradigm.get(paradigm_id, [])
        supporting_papers = []
        for paper in papers:
            text = " ".join([paper.get("title", ""), paper.get("finding", ""), " ".join(paper.get("keywords", [])), paper.get("topic", "")]).lower()
            if any(token in text for token in paradigm_id.split("_")):
                supporting_papers.append(paper)
        if not supporting_papers:
            supporting_papers = papers[:2]
        detail = {
            "id": paradigm_id,
            "name": candidate["name"],
            "description": candidate.get("description", ""),
            "required_data": candidate.get("required_data", []),
            "expected_outputs": candidate.get("outputs", []),
            "missing_data": candidate.get("missing_data", []),
            "selection": candidate,
            "evaluation": evaluation_map.get(paradigm_id, {}),
            "supporting_papers": supporting_papers[:5],
            "innovation_points": [item for item in innovations if item.get("paradigm_id") == paradigm_id or paradigm_id in item.get("paradigm_id", "").split("+")],
            "code_resources": code_map.get(paradigm_id, []),
            "generated_code": generated_items[0] if generated_items else {},
            "generated_experiment_code": generated_items,
            "execution": execution_items[0] if execution_items else {},
            "executions": execution_items,
        }
        details.append(detail)
    return details


def write_report(
    ctx: ResearchContext,
    papers: list[dict[str, Any]],
    innovations: list[dict[str, Any]],
    innovation_scores: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    code_map: dict[str, Any],
    generated_code: list[dict[str, Any]],
    execution_results: list[dict[str, Any]],
    figures: dict[str, str],
    innovation_execution_update: dict[str, Any] | None = None,
) -> None:
    best = evaluations[0] if evaluations else {}
    execution_map = {item.get("paradigm"): item for item in execution_results}
    generated_map = {item.get("paradigm"): item for item in generated_code}
    generated_by_experiment: dict[str, list[dict[str, Any]]] = {}
    for item in generated_code:
        generated_by_experiment.setdefault(str(item.get("experiment_id", "") or item.get("innovation_id", "")), []).append(item)
    execution_by_experiment: dict[str, list[dict[str, Any]]] = {}
    for item in execution_results:
        execution_by_experiment.setdefault(str(item.get("experiment_id", "") or item.get("innovation_id", "")), []).append(item)
    data_root = str(ctx.data_root or "")
    fmri_output_root = str(ctx.fmri_output_root or "")
    updates_by_id = {
        str(item.get("id", "")): item
        for item in (innovation_execution_update or {}).get("updated_innovations", [])
        if isinstance(item, dict)
    }
    lines = [
        "# 神经科学研究 Agent 中文报告",
        "",
        f"- 用户任务：{ctx.prompt}",
        f"- 输入数据目录：{data_root}",
        f"- 文献报告：{ctx.output_dir / 'papers' / 'literature_report.md'}",
        f"- KG evidence 文档：{ctx.output_dir / 'knowledge_graph' / 'kg_context.md'}",
        f"- 步骤过程文档：{ctx.output_dir / 'steps' / 'manifest.md'}",
    ]
    if fmri_output_root and fmri_output_root != data_root:
        lines.append(f"- 处理后 fMRI 输出目录：{fmri_output_root}")
    lines.extend([
        f"- 被试：{ctx.subject or ''}",
        f"- Session：{ctx.session or ''}",
        "",
        "## 最优实验路线",
        "",
        f"- {best.get('name', '')}（`{best.get('id', '')}`）：{best.get('score_total', '')}/100",
        f"- 当前数据是否可执行：{best.get('executable', '')}",
        f"- 执行状态：{best.get('execution_status', '')}",
        f"- 缺失数据：{best.get('missing_data', [])}",
        "",
        "## 图表与 3D 结果",
        "",
    ])
    for name, path in figures.items():
        lines.append(f"- {name}: {path}")
    lines.extend(["", "## 检索文献", ""])
    for paper in papers:
        lines.append(f"- {paper.get('title', '')} | {paper.get('url', '')}")
    lines.extend(["", "## 原始创新点", ""])
    for item in innovations:
        lines.append(f"- `{item.get('id', '')}` {item.get('paradigm_name', '')}: {item.get('innovation_point', '')}")
        lines.append(f"  假设：{item.get('hypothesis', '')}")
        if item.get("kg_evidence"):
            lines.append(f"  KG evidence：{'; '.join([str(x) for x in item.get('kg_evidence', [])[:2]])}")
        if item.get("local_data_feasibility_zh"):
            lines.append(f"  本地数据可行性：{item.get('local_data_feasibility_zh', '')}")
    lines.extend(["", "## 创新点实验目录", ""])
    for item in innovations:
        experiment_id = safe_path_id(str(item.get("id", "")), "innovation")
        generated_items = generated_by_experiment.get(experiment_id, [])
        execution_items = execution_by_experiment.get(experiment_id, [])
        experiment_dir = generated_items[0].get("experiment_dir", "") if generated_items else ""
        lines.append(f"### `{experiment_id}`")
        lines.append(f"- 实验文件夹：{experiment_dir}")
        lines.append(f"- 绑定实验路线：{item.get('paradigm_id', '')}")
        for generated in generated_items:
            matched_execution = next((record for record in execution_items if record.get("paradigm") == generated.get("paradigm")), {})
            lines.append(f"- `{generated.get('paradigm', '')}` py代码：{generated.get('script', generated.get('path', ''))}")
            lines.append(f"  执行状态：{matched_execution.get('status', 'not_run')}，结果 JSON：{matched_execution.get('result_json', '')}")
    lines.extend(["", "## 根据真实执行结果反向修正创新点", ""])
    if innovation_execution_update:
        lines.append(f"- 总体结论：{innovation_execution_update.get('overall_update_zh', '')}")
        lines.append(f"- 更新方法：{innovation_execution_update.get('method', '')}")
    for item in innovations:
        update = updates_by_id.get(str(item.get("id", ""))) or item.get("experimental_update", {})
        lines.append(f"### `{item.get('id', '')}`")
        lines.append(f"- 原始创新点：{item.get('innovation_point', '')}")
        lines.append(f"- 执行结果解释：{update.get('result_interpretation_zh', '')}")
        lines.append(f"- 修正后假设：{update.get('updated_hypothesis_zh', item.get('hypothesis', ''))}")
        lines.append(f"- 修正后创新点：{update.get('updated_innovation_point_zh', item.get('innovation_point', ''))}")
        lines.append(f"- 下一步实验：{update.get('next_experiment_zh', '')}")
        lines.append(f"- 置信度：{update.get('confidence', '')}")
    lines.extend(["", "## 创新点评分", "", "| 创新点 | 总分 | 新颖性 | 可行性 | 科学价值 | 风险控制 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in innovation_scores:
        lines.append(
            f"| {row['id']} | {row['score_total']} | {row['novelty_score']} | {row['feasibility_score']} | "
            f"{row['scientific_value_score']} | {row['risk_control_score']} |"
        )
    lines.extend(["", "## 实验路线评分", "", "| 实验路线 | 可执行 | 分数 | 缺失数据 |", "| --- | --- | ---: | --- |"])
    for row in evaluations:
        lines.append(f"| {row['id']} | {row['executable']} | {row['score_total']} | {row['missing_data']} |")
    lines.extend(["", "## 实验路线执行详情", ""])
    for row in evaluations:
        execution = execution_map.get(row["id"], {})
        generated = generated_map.get(row["id"], {})
        lines.append(f"### {row['name']} (`{row['id']}`)")
        lines.append(f"- 分数：{row['score_total']}/100")
        lines.append(f"- 生成代码：{generated.get('path', '')}")
        lines.append(f"- 执行：{execution.get('status', 'not_run')} returncode={execution.get('returncode', '')}")
        lines.append(f"- 结果 JSON：{execution.get('result_json', '')}")
        lines.append(f"- 缺失数据：{row.get('missing_data', [])}")
    lines.extend(["", "## 代码资源", ""])
    for paradigm_id, resources in code_map.items():
        lines.append(f"### {paradigm_id}")
        for item in resources:
            lines.append(f"- {item.get('name', '')}: {item.get('url', '')}")
    write_text(ctx.output_dir / "final_report.md", "\n".join(lines))


def run_research_flow(ctx: ResearchContext, allow_network: bool = False) -> dict[str, Any]:
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    recorder = StepRecorder(ctx.output_dir)
    planner_agent = PlannerAgent()
    scientist_agent = ScientistAgent()
    coder_agent = CoderAgent()
    reviewer_agent = ReviewerAgent()
    analyst_agent = AnalystAgent()

    progress_log("start", "research_flow_orchestrator", f"开始执行研究任务: {ctx.prompt}")
    progress_log("start", "research_flow_orchestrator", f"输出目录: {ctx.output_dir}")
    progress_log("start", "research_flow_orchestrator", f"输入数据目录: {ctx.data_root or ctx.fmri_output_root or '未指定'}")
    expected_processed_root = planner_agent.expected_processed_root(ctx.raw_fmri_input_root, ctx.fmri_result_root, ctx.fmri_output_root or ctx.data_root)
    if ctx.raw_fmri_input_root or expected_processed_root:
        step_started = time.time()
        progress_log("fmri_preprocessing", "planner_agent.ensure_fmri_data", "检查处理后的 fMRI derivatives 和 QC 是否完整")
        preprocessing_status = planner_agent.ensure_fmri_data(
            ctx.raw_fmri_input_root,
            ctx.fmri_result_root,
            expected_processed_root,
            ctx.prompt,
            ctx.output_dir,
            ctx.fmri_local_agent_script,
        )
        preprocessing_path = ctx.output_dir / "data" / "fmri_preprocessing_status.json"
        write_json(preprocessing_path, preprocessing_status)
        processed_root_text = preprocessing_status.get("processed_root") or ""
        if processed_root_text:
            ctx.data_root = Path(processed_root_text)
            ctx.fmri_output_root = Path(processed_root_text)
        complete_after_gate = bool(preprocessing_status.get("after", {}).get("complete") or preprocessing_status.get("complete"))
        recorder.record(
            "fmri_preprocessing",
            {
                "status_json": str(preprocessing_path),
                "processed_root": processed_root_text,
                "complete": complete_after_gate,
                "used_existing_processed_data": preprocessing_status.get("used_existing_processed_data", False),
                "preprocessing_status": preprocessing_status,
            },
            step_started,
        )
        progress_log(
            "fmri_preprocessing",
            "planner_agent.ensure_fmri_data",
            f"fMRI 预处理门控完成: processed_root={processed_root_text or 'NA'}, complete={complete_after_gate}",
        )
        if not complete_after_gate:
            raise RuntimeError(f"处理后的 fMRI derivatives/QC 不完整，已停止后续实验分析。详情见 {preprocessing_path}")

    step_started = time.time()
    progress_log("prompt_and_configuration", "configuration_agent", "记录任务配置")
    recorder.record(
        "prompt_and_configuration",
        {
            "prompt": ctx.prompt,
            "data_root": str(ctx.data_root) if ctx.data_root else "",
            "fmri_output_root": str(ctx.fmri_output_root) if ctx.fmri_output_root else "",
            "raw_fmri_input_root": str(ctx.raw_fmri_input_root) if ctx.raw_fmri_input_root else "",
            "fmri_result_root": str(ctx.fmri_result_root) if ctx.fmri_result_root else "",
            "subject": ctx.subject or "",
            "session": ctx.session or "",
            "max_papers": ctx.max_papers,
            "max_code_results": ctx.max_code_results,
            "ollama_url": ctx.ollama_url,
            "ollama_model": ctx.ollama_model,
            "allow_network": allow_network,
            "run_experiments": ctx.run_experiments,
        },
        step_started,
    )
    progress_log("prompt_and_configuration", "configuration_agent", "配置记录完成")

    step_started = time.time()
    progress_log("literature_retrieval", "scientist_agent.retrieve_literature", f"开始 LLM 文献检索规划、筛选和证据评价: max_papers={ctx.max_papers}, allow_network={allow_network}")
    literature_bundle = scientist_agent.retrieve_literature(
        ctx.prompt,
        max_papers=ctx.max_papers,
        allow_network=allow_network,
        ollama_url=ctx.ollama_url,
        ollama_model_name=ctx.ollama_model,
    )
    papers = literature_bundle["papers"]
    papers_path = ctx.output_dir / "papers" / "retrieved_papers.json"
    papers_md_path = ctx.output_dir / "papers" / "retrieved_papers.md"
    report_path = ctx.output_dir / "papers" / "literature_report.md"
    plan_path = ctx.output_dir / "papers" / "literature_search_plan.json"
    screening_path = ctx.output_dir / "papers" / "literature_screening.json"
    target_candidates_path = ctx.output_dir / "papers" / "target_candidates.json"
    write_json(papers_path, papers)
    write_payload_markdown(papers_md_path, "Retrieved Papers", {"papers": papers})
    write_text(report_path, literature_bundle["report_markdown"])
    write_json(plan_path, literature_bundle.get("search_plan", {}))
    write_json(target_candidates_path, literature_bundle.get("target_candidates", []))
    write_json(
        screening_path,
        {
            "requested_max_papers": literature_bundle.get("requested_max_papers", ctx.max_papers),
            "returned_paper_count": literature_bundle.get("returned_paper_count", len(papers)),
            "llm_screening": literature_bundle.get("llm_screening", {}),
            "source_paper_selection": literature_bundle.get("source_paper_selection", {}),
            "online_source_counts": literature_bundle.get("online_source_counts", {}),
            "warnings": literature_bundle.get("warnings", {}),
            "candidate_count": literature_bundle.get("candidate_count", 0),
        },
    )
    recorder.record(
        "literature_retrieval",
        {
            "paper_count": len(papers),
            "output": str(papers_path),
            "report": str(report_path),
            "search_plan": str(plan_path),
            "screening": str(screening_path),
            "target_candidates": str(target_candidates_path),
            "online_source_counts": literature_bundle.get("online_source_counts", {}),
            "candidate_count": literature_bundle.get("candidate_count", 0),
            "requested_max_papers": literature_bundle.get("requested_max_papers", ctx.max_papers),
            "returned_paper_count": literature_bundle.get("returned_paper_count", len(papers)),
            "warnings": literature_bundle.get("warnings", {}),
            "papers": papers,
        },
        step_started,
    )
    progress_log(
        "literature_retrieval",
        "scientist_agent.retrieve_literature",
        f"论文检索完成: requested={ctx.max_papers}, candidate_count={literature_bundle.get('candidate_count', 0)}, paper_count={len(papers)}, report={report_path}, output={papers_path}",
    )

    step_started = time.time()
    progress_log("data_inventory", "planner_agent.inspect_data", "开始扫描输入数据")
    inventory = planner_agent.inspect_data(ctx.data_root, ctx.fmri_output_root, ctx.subject, ctx.session)
    inventory_path = ctx.output_dir / "data" / "data_inventory.json"
    inventory_md_path = ctx.output_dir / "data" / "data_inventory.md"
    write_json(inventory_path, inventory)
    write_payload_markdown(inventory_md_path, "Data Inventory", inventory)
    data_types = planner_agent.available_data_types(inventory)
    recorder.record(
        "data_inventory",
        {
            "output": str(inventory_path),
            "available_data_types": sorted(data_types),
            "modality_count": len(data_types),
            "inventory": inventory,
        },
        step_started,
    )
    progress_log("data_inventory", "planner_agent.inspect_data", f"数据扫描完成: modality_count={len(data_types)}, output={inventory_path}")

    step_started = time.time()
    progress_log("analysis_route_selection", "planner_agent.classify_paradigms", "开始选择候选实验路线")
    candidates = planner_agent.classify_paradigms(ctx.prompt, data_types)
    candidates_path = ctx.output_dir / "paradigms" / "candidate_paradigms.json"
    candidates_md_path = ctx.output_dir / "paradigms" / "candidate_analysis_routes.md"
    write_json(candidates_path, candidates)
    write_payload_markdown(candidates_md_path, "Candidate Analysis Routes", {"candidate_count": len(candidates), "candidates": candidates})
    recorder.record(
        "analysis_route_selection",
        {
            "candidate_count": len(candidates),
            "output": str(candidates_path),
            "top_candidates": candidates[:5],
            "all_candidates": candidates,
        },
        step_started,
    )
    progress_log("analysis_route_selection", "planner_agent.classify_paradigms", f"实验路线选择完成: candidate_count={len(candidates)}, output={candidates_path}")

    step_started = time.time()
    progress_log("kg_context_retrieval", "scientist_agent.retrieve_kg_context", "开始构建 KG evidence 与本地数据可行性上下文")
    kg_context = build_kg_context(ctx.prompt, papers, candidates, data_types)
    kg_context_path = ctx.output_dir / "knowledge_graph" / "kg_context.json"
    kg_context_md_path = ctx.output_dir / "knowledge_graph" / "kg_context.md"
    write_json(kg_context_path, kg_context)
    write_text(kg_context_md_path, kg_context_to_markdown(kg_context))
    recorder.record(
        "kg_context_retrieval",
        {
            "kg_context_json": str(kg_context_path),
            "kg_context_markdown": str(kg_context_md_path),
            "mode": kg_context.get("mode", ""),
            "source_count": len(kg_context.get("sources", [])),
            "matched_hypothesis_count": len(kg_context.get("matched_hypotheses", [])),
            "matched_claim_count": len(kg_context.get("matched_claims", [])),
            "literature_claim_count": len(kg_context.get("literature_claims", [])),
            "region_terms": kg_context.get("region_terms", []),
            "kg_context": kg_context,
        },
        step_started,
    )
    progress_log(
        "kg_context_retrieval",
        "scientist_agent.retrieve_kg_context",
        f"KG evidence 构建完成: mode={kg_context.get('mode', '')}, sources={len(kg_context.get('sources', []))}, output={kg_context_path}",
    )

    step_started = time.time()
    progress_log("innovation_extraction", "scientist_agent.derive_innovations", "开始提取创新点: LLM + KG evidence + local data feasibility 共同生成 idea")
    innovations = scientist_agent.derive_innovations(
        ctx.prompt,
        papers,
        candidates,
        ollama_url=ctx.ollama_url,
        ollama_model_name=ctx.ollama_model,
        kg_context=kg_context,
    )
    innovations_path = ctx.output_dir / "innovation" / "innovation_points.json"
    innovations_md_path = ctx.output_dir / "innovation" / "innovation_points.md"
    write_json(innovations_path, innovations)
    write_payload_markdown(innovations_md_path, "Innovation Points", {"innovation_count": len(innovations), "innovations": innovations})
    innovation_process_json_path = ctx.output_dir / "innovation" / "innovation_generation_process.json"
    innovation_process_md_path = ctx.output_dir / "innovation" / "innovation_generation_process.md"
    write_json(
        innovation_process_json_path,
        {
            "说明": "本文件记录创新点、每个 idea 的自我反思过程、pairwise tournament 排序过程，以及实验结果反向更新占位。",
            "innovations": innovations,
        },
    )
    write_text(innovation_process_md_path, scientist_agent.build_innovation_document(ctx.prompt, innovations))
    recorder.record(
        "innovation_extraction",
        {
            "innovation_count": len(innovations),
            "output": str(innovations_path),
            "output_markdown": str(innovations_md_path),
            "process_json": str(innovation_process_json_path),
            "process_markdown": str(innovation_process_md_path),
            "innovations": innovations,
        },
        step_started,
    )
    progress_log("innovation_extraction", "scientist_agent.derive_innovations", f"创新点提取完成: innovation_count={len(innovations)}, output={innovations_path}")

    step_started = time.time()
    progress_log("code_search_and_generation", "coder_agent.search_and_generate", f"开始按创新点生成可执行 py 实验代码: innovation_count={len(innovations)}")
    candidate_by_id = {item["id"]: item for item in candidates}
    code_map: dict[str, list[dict[str, Any]]] = {}
    generated_code = []
    experiment_manifests = []
    experiment_root = ctx.output_dir / "experiments"
    experiment_root.mkdir(parents=True, exist_ok=True)

    for innovation_index, innovation in enumerate(innovations, start=1):
        innovation_id = safe_path_id(str(innovation.get("id") or f"innovation_{innovation_index:02d}"), f"innovation_{innovation_index:02d}")
        bound_ids = bound_paradigm_ids(innovation, candidate_by_id)
        this_experiment_dir = experiment_root / innovation_id
        this_experiment_dir.mkdir(parents=True, exist_ok=True)
        experiment_manifest_payload = {
            "experiment_id": innovation_id,
            "innovation_id": innovation.get("id", innovation_id),
            "innovation_point_zh": innovation.get("innovation_point", ""),
            "hypothesis_zh": innovation.get("hypothesis", ""),
            "bound_paradigm_ids": bound_ids,
            "experiment_dir": str(this_experiment_dir),
        }
        write_json(this_experiment_dir / "experiment_manifest.json", experiment_manifest_payload)
        write_payload_markdown(this_experiment_dir / "experiment_manifest.md", "Experiment Manifest", experiment_manifest_payload)
        literature_context_payload = build_literature_context(innovation, papers)
        write_json(this_experiment_dir / "literature_context.json", literature_context_payload)
        write_payload_markdown(this_experiment_dir / "literature_context.md", "Literature And KG Context", literature_context_payload)
        experiment_records = []
        progress_log(
            "code_search_and_generation",
            "coder_agent.search_and_generate",
            f"({innovation_index}/{len(innovations)}) 生成创新点实验: innovation={innovation_id}, analysis_routes={'+'.join(bound_ids)}",
        )
        for paradigm_id in bound_ids:
            paradigm = candidate_by_id[paradigm_id]
            if paradigm_id not in code_map:
                progress_log("code_search_and_generation", "coder_agent.search_code", f"检索代码资源: analysis_route={paradigm_id}")
                code_map[paradigm_id] = coder_agent.search_code(paradigm_id, ctx.prompt, max_results=ctx.max_code_results, allow_network=allow_network)
            progress_log(
                "code_search_and_generation",
                "coder_agent.generate_code",
                f"生成可执行 py 实验代码: innovation={innovation_id}, analysis_route={paradigm_id}",
            )
            script_path = coder_agent.generate_code(paradigm, this_experiment_dir, linked_innovations=[innovation])
            record = {
                "experiment_id": innovation_id,
                "innovation_id": innovation.get("id", innovation_id),
                "experiment_dir": str(this_experiment_dir),
                "innovation_point": innovation.get("innovation_point", ""),
                "hypothesis": innovation.get("hypothesis", ""),
                "paradigm": paradigm_id,
                "path": str(script_path),
                "script": str(script_path),
                "execution_dir": str(this_experiment_dir),
                "class_pipeline_plan": str(this_experiment_dir / f"{paradigm_id}_class_pipeline_plan.json"),
                "linked_innovation_ids": [innovation.get("id", innovation_id)],
            }
            generated_code.append(record)
            experiment_records.append(record)
        write_json(this_experiment_dir / "generated_code_manifest.json", experiment_records)
        write_payload_markdown(
            this_experiment_dir / "generated_code_manifest.md",
            "Generated Code Manifest",
            {"script_count": len(experiment_records), "generated_code": experiment_records},
        )
        experiment_plan_payload = build_experiment_plan(innovation, bound_ids, experiment_records)
        write_json(this_experiment_dir / "experiment_plan.json", experiment_plan_payload)
        write_payload_markdown(this_experiment_dir / "experiment_plan.md", "Experiment Plan", experiment_plan_payload)
        experiment_manifests.append(
            {
                "experiment_id": innovation_id,
                "innovation_id": innovation.get("id", innovation_id),
                "experiment_dir": str(this_experiment_dir),
                "bound_paradigm_ids": bound_ids,
                "generated_code": experiment_records,
            }
        )
    code_path = experiment_root / "code_resources.json"
    code_md_path = experiment_root / "code_resources.md"
    write_json(code_path, code_map)
    write_payload_markdown(code_md_path, "Code Resources", {"code_resources": code_map})
    experiments_manifest_path = experiment_root / "experiments_manifest.json"
    experiments_manifest_md_path = experiment_root / "experiments_manifest.md"
    write_json(experiments_manifest_path, experiment_manifests)
    write_payload_markdown(
        experiments_manifest_md_path,
        "Experiments Manifest",
        {"experiment_count": len(experiment_manifests), "experiments": experiment_manifests},
    )
    generated_path = experiment_root / "generated_code_manifest.json"
    generated_md_path = experiment_root / "generated_code_manifest.md"
    write_json(generated_path, generated_code)
    write_payload_markdown(generated_md_path, "Generated Code Manifest", {"script_count": len(generated_code), "generated_code": generated_code})
    recorder.record(
        "code_search_and_generation",
        {
            "code_resources_output": str(code_path),
            "code_resources_markdown": str(code_md_path),
            "experiments_manifest": str(experiments_manifest_path),
            "experiments_manifest_markdown": str(experiments_manifest_md_path),
            "generated_code_manifest": str(generated_path),
            "generated_code_manifest_markdown": str(generated_md_path),
            "code_resources": code_map,
            "experiments": experiment_manifests,
            "generated_code": generated_code,
        },
        step_started,
    )
    progress_log("code_search_and_generation", "coder_agent.search_and_generate", f"按创新点生成实验完成: experiment_count={len(experiment_manifests)}, script_count={len(generated_code)}, manifest={experiments_manifest_path}")

    step_started = time.time()
    execution_results: list[dict[str, Any]] = []
    if ctx.run_experiments:
        progress_log("experiment_execution", "analyst_agent.run_generated_experiments", f"开始执行生成实验 py 代码: script_count={len(generated_code)}")
        execution_results = analyst_agent.run_experiments(generated_code, ctx.output_dir, ctx.data_root or ctx.fmri_output_root, ctx.subject, ctx.session)
    else:
        progress_log("experiment_execution", "analyst_agent.run_generated_experiments", "跳过生成实验执行")
    execution_path = experiment_root / "execution_manifest.json"
    execution_md_path = experiment_root / "execution_manifest.md"
    write_json(execution_path, execution_results)
    write_payload_markdown(execution_md_path, "Execution Manifest", {"result_count": len(execution_results), "execution_results": execution_results})
    executions_by_experiment: dict[str, list[dict[str, Any]]] = {}
    for item in execution_results:
        experiment_id = str(item.get("experiment_id", "") or "")
        if experiment_id:
            executions_by_experiment.setdefault(experiment_id, []).append(item)
    for experiment in experiment_manifests:
        experiment_id = str(experiment.get("experiment_id", ""))
        experiment_dir = Path(str(experiment.get("experiment_dir", "")))
        if experiment_id and str(experiment_dir):
            experiment_execution_payload = {
                "experiment_id": experiment_id,
                "innovation_id": experiment.get("innovation_id", experiment_id),
                "bound_paradigm_ids": experiment.get("bound_paradigm_ids", []),
                "executions": executions_by_experiment.get(experiment_id, []),
            }
            write_json(experiment_dir / "execution_manifest.json", experiment_execution_payload)
            write_payload_markdown(experiment_dir / "execution_manifest.md", "Experiment Execution Manifest", experiment_execution_payload)
    recorder.record(
        "experiment_execution",
        {
            "run_experiments": ctx.run_experiments,
            "execution_manifest": str(execution_path),
            "execution_manifest_markdown": str(execution_md_path),
            "execution_results": execution_results,
        },
        step_started,
    )
    progress_log("experiment_execution", "analyst_agent.run_generated_experiments", f"实验执行阶段完成: result_count={len(execution_results)}, manifest={execution_path}")

    step_started = time.time()
    progress_log("innovation_feedback", "analyst_agent.update_innovations_from_execution", "开始根据实验/计算结果反向更新创新点")
    innovation_execution_update = analyst_agent.update_innovations_from_execution(
        ctx.prompt,
        innovations,
        execution_results,
        ollama_url=ctx.ollama_url,
        ollama_model_name=ctx.ollama_model,
    )
    write_json(innovations_path, innovations)
    innovation_feedback_json_path = ctx.output_dir / "innovation" / "innovation_feedback_update.json"
    innovation_process_final_md_path = ctx.output_dir / "innovation" / "innovation_generation_process_with_feedback.md"
    updated_innovations = innovation_execution_update.get("updated_innovations", []) if isinstance(innovation_execution_update, dict) else []
    write_json(
        innovation_feedback_json_path,
        {
            "说明": "本文件记录实验/计算执行结果对创新点的反向更新。",
            "method": innovation_execution_update.get("method", "") if isinstance(innovation_execution_update, dict) else "",
            "overall_update_zh": innovation_execution_update.get("overall_update_zh", "") if isinstance(innovation_execution_update, dict) else "",
            "updated_innovations": updated_innovations,
            "updated_innovation_count": len(updated_innovations),
            "execution_update": innovation_execution_update,
            "innovations": innovations,
        },
    )
    write_json(
        innovation_process_json_path,
        {
            "说明": "本文件记录创新点、每个 idea 的自我反思过程、pairwise tournament 排序过程，以及实验结果反向更新结果。",
            "execution_update": innovation_execution_update,
            "innovations": innovations,
        },
    )
    write_text(innovation_process_final_md_path, analyst_agent.build_innovation_document(ctx.prompt, innovations, innovation_execution_update))
    recorder.record(
        "innovation_feedback",
        {
            "feedback_json": str(innovation_feedback_json_path),
            "process_markdown": str(innovation_process_final_md_path),
            "execution_update": innovation_execution_update,
            "innovations": innovations,
        },
        step_started,
    )
    progress_log("innovation_feedback", "analyst_agent.update_innovations_from_execution", f"创新点反向更新完成: output={innovation_feedback_json_path}")

    step_started = time.time()
    progress_log("analysis_route_scoring", "reviewer_agent.evaluate_paradigms", "开始实验路线评分")
    evaluations = reviewer_agent.evaluate_paradigms(candidates, papers, code_map, innovations, execution_results)
    scores_json = ctx.output_dir / "paradigms" / "paradigm_scores.json"
    scores_csv = ctx.output_dir / "paradigms" / "paradigm_scores.csv"
    scores_md = ctx.output_dir / "paradigms" / "analysis_route_scores.md"
    write_json(scores_json, evaluations)
    write_csv(scores_csv, evaluations)
    write_payload_markdown(scores_md, "Analysis Route Scores", {"analysis_route_count": len(evaluations), "evaluations": evaluations})
    recorder.record(
        "analysis_route_scoring",
        {
            "scores_json": str(scores_json),
            "scores_csv": str(scores_csv),
            "scores_markdown": str(scores_md),
            "best_paradigm": evaluations[0] if evaluations else None,
            "best_analysis_route": evaluations[0] if evaluations else None,
            "evaluations": evaluations,
        },
        step_started,
    )
    progress_log("analysis_route_scoring", "reviewer_agent.evaluate_paradigms", f"实验路线评分完成: best={evaluations[0]['id'] if evaluations else 'NA'}, output={scores_json}")

    step_started = time.time()
    progress_log("innovation_scoring", "reviewer_agent.evaluate_innovations", "开始创新点评分")
    innovation_scores = reviewer_agent.evaluate_innovations(innovations, evaluations, execution_results)
    innovation_scores_path = ctx.output_dir / "innovation" / "innovation_scores.json"
    innovation_scores_md_path = ctx.output_dir / "innovation" / "innovation_scores.md"
    write_json(innovation_scores_path, innovation_scores)
    write_payload_markdown(
        innovation_scores_md_path,
        "Innovation Scores",
        {"innovation_count": len(innovation_scores), "innovation_scores": innovation_scores},
    )
    recorder.record(
        "innovation_scoring",
        {
            "scores_json": str(innovation_scores_path),
            "scores_markdown": str(innovation_scores_md_path),
            "best_innovation": innovation_scores[0] if innovation_scores else None,
            "innovation_scores": innovation_scores,
        },
        step_started,
    )
    progress_log("innovation_scoring", "reviewer_agent.evaluate_innovations", f"创新点评分完成: count={len(innovation_scores)}, output={innovation_scores_path}")

    step_started = time.time()
    progress_log("analysis_route_details", "reviewer_agent.build_analysis_route_details", "开始汇总实验路线详情")
    detail_map = build_paradigm_details(candidates, papers, innovations, code_map, generated_code, execution_results, evaluations)
    details_path = ctx.output_dir / "paradigms" / "paradigm_details.json"
    details_md_path = ctx.output_dir / "paradigms" / "analysis_route_details.md"
    write_json(details_path, detail_map)
    write_payload_markdown(details_md_path, "Analysis Route Details", {"analysis_route_count": len(detail_map), "details": detail_map})
    for detail in detail_map:
        evaluation = detail.get("evaluation", {})
        execution = detail.get("execution", {})
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ANALYSIS_ROUTE] "
            f"{detail['id']} | score={evaluation.get('score_total', 'NA')} | "
            f"execution={execution.get('status', 'not_run')} | "
            f"result={execution.get('result_json', '')}",
            flush=True,
        )
    recorder.record(
        "analysis_route_details",
        {
            "details_json": str(details_path),
            "details_markdown": str(details_md_path),
            "analysis_route_count": len(detail_map),
            "details": detail_map,
        },
        step_started,
    )
    progress_log("analysis_route_details", "reviewer_agent.build_analysis_route_details", f"实验路线详情汇总完成: output={details_path}")

    step_started = time.time()
    progress_log("visualization", "analyst_agent.plot_scores", "开始生成图表和收集 3D connectome HTML")
    figures = analyst_agent.plot_scores(evaluations, ctx.output_dir / "figures")
    figures.update(analyst_agent.collect_connectome_figures(execution_results))
    figures_json = ctx.output_dir / "figures" / "figures.json"
    figures_md = ctx.output_dir / "figures" / "figures.md"
    write_json(figures_json, figures)
    write_payload_markdown(figures_md, "Figures", {"figure_count": len(figures), "figures": figures})
    recorder.record(
        "visualization",
        {
            "figures_json": str(figures_json),
            "figures_markdown": str(figures_md),
            "figures": figures,
        },
        step_started,
    )
    progress_log("visualization", "analyst_agent.plot_scores", f"可视化完成: figure_count={len(figures)}, output={figures_json}")

    step_started = time.time()
    progress_log("final_report", "analyst_agent.write_report", "开始写入最终报告")
    write_report(ctx, papers, innovations, innovation_scores, evaluations, code_map, generated_code, execution_results, figures, innovation_execution_update)
    report_path = ctx.output_dir / "final_report.md"
    recorder.record(
        "final_report",
        {
            "report": str(report_path),
            "manifest": str(recorder.root / "manifest.json"),
            "manifest_markdown": str(recorder.root / "manifest.md"),
        },
        step_started,
    )
    progress_log("final_report", "analyst_agent.write_report", f"最终报告完成: {report_path}")
    status = {
        "returncode": 0,
        "prompt": ctx.prompt,
        "output_dir": str(ctx.output_dir),
        "best_paradigm": evaluations[0] if evaluations else None,
        "best_analysis_route": evaluations[0] if evaluations else None,
        "figures": figures,
        "innovation_points": str(innovations_path),
        "innovation_points_markdown": str(innovations_md_path),
        "innovation_generation_process": str(innovation_process_json_path),
        "innovation_generation_process_markdown": str(innovation_process_md_path),
        "innovation_feedback_update": str(innovation_feedback_json_path),
        "kg_context": str(kg_context_path),
        "kg_context_markdown": str(kg_context_md_path),
        "innovation_generation_process_with_feedback_markdown": str(innovation_process_final_md_path),
        "innovation_scores": str(innovation_scores_path),
        "innovation_scores_markdown": str(innovation_scores_md_path),
        "innovation_experiments_manifest": str(experiments_manifest_path),
        "innovation_experiments_manifest_markdown": str(experiments_manifest_md_path),
        "execution_manifest": str(execution_path),
        "execution_manifest_markdown": str(execution_md_path),
        "paradigm_details": str(details_path),
        "analysis_route_details": str(details_path),
        "analysis_route_details_markdown": str(details_md_path),
        "analysis_route_scores_markdown": str(scores_md),
        "final_report": str(report_path),
        "steps_manifest": str(recorder.root / "manifest.json"),
        "steps_manifest_markdown": str(recorder.root / "manifest.md"),
        "elapsed_seconds": int(time.time() - started),
    }
    write_json(ctx.output_dir / "run_status.json", status)
    write_payload_markdown(ctx.output_dir / "run_status.md", "Run Status", status)
    return status
