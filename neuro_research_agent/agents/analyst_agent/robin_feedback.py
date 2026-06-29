from __future__ import annotations

from typing import Any

DATA_INTERPRETATION_SYSTEM_MESSAGE = (
    "你是一个严谨的实验结果解释 agent。你的任务是只根据已有 result.json、QC 和图表摘要，"
    "解释实验结果如何约束原始科学假设；不能编造显著性、群体结论或未执行的实验。"
)

DATA_INTERPRETATION_CONTENT_TEMPLATE = (
    "研究目标：{goal}\n\n"
    "实验结果摘要：\n{result_summary}\n\n"
    "请输出四部分：\n"
    "1. 已检验的机制成分；\n"
    "2. 关键发现和量化指标；\n"
    "3. 结果提出的新问题；\n"
    "4. 可由结果支持的机制洞察，以及当前不能检验的部分。"
)

FOLLOWUP_SYSTEM_MESSAGE = (
    "你是一个科研策略 agent。你的任务是根据实验结果解释提出后续实验或假设修正，"
    "优先处理结果暴露出的数据缺口、ROI 覆盖不足、QC 风险和替代解释。"
)

FOLLOWUP_CONTENT_TEMPLATE = (
    "研究目标：{goal}\n\n"
    "结果摘要：\n{analysis_summary}\n\n"
    "机制洞察：\n{mechanistic_insights}\n\n"
    "新问题：\n{questions_raised}\n\n"
    "请给出：修正后假设、修正后创新点、下一步实验、置信度。"
)


def feedback_source_metadata() -> dict[str, Any]:
    return {
        "source": "Robin: A multi-agent system for automating scientific discovery",
        "implementation": "local_analyst_agent",
        "uses_edison_platform": False,
        "reused_components": [
            "result_interpretation",
            "mechanistic_insight_extraction",
            "followup_hypothesis_revision",
            "result_constrained_idea_update",
        ],
    }


def build_robin_feedback_prompt(goal: str, result_summary: str, questions_raised: str = "", mechanistic_insights: str = "") -> dict[str, str]:
    return {
        "system": DATA_INTERPRETATION_SYSTEM_MESSAGE,
        "content": DATA_INTERPRETATION_CONTENT_TEMPLATE.format(goal=goal, result_summary=result_summary),
        "followup_system": FOLLOWUP_SYSTEM_MESSAGE,
        "followup_content": FOLLOWUP_CONTENT_TEMPLATE.format(
            goal=goal,
            analysis_summary=result_summary,
            mechanistic_insights=mechanistic_insights or "由当前 result.json 指标和 QC 摘要推断。",
            questions_raised=questions_raised or "哪些指标真正支持原假设，哪些机制成分因数据覆盖不足而应暂缓解释？",
        ),
    }


def attach_local_feedback_prompts(payload: dict[str, Any], goal: str) -> dict[str, Any]:
    updates = payload.get("updated_innovations", [])
    prompt_records: list[dict[str, str]] = []
    if isinstance(updates, list):
        for item in updates:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("result_interpretation_zh", ""))
            prompts = build_robin_feedback_prompt(
                goal,
                summary,
                questions_raised=str(item.get("next_experiment_zh", "")),
                mechanistic_insights=str(item.get("updated_hypothesis_zh", "")),
            )
            prompt_records.append(
                {
                    "id": str(item.get("id", "")),
                    "result_interpretation_prompt": prompts["content"],
                    "followup_revision_prompt": prompts["followup_content"],
                }
            )
    payload["local_robin_feedback_prompts"] = prompt_records
    return payload
