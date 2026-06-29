#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neuro_research_agent.core.types import ResearchContext


def progress_log(stage: str, agent: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{stage}] agent={agent} | {message}", flush=True)


def configure_runtime_cache() -> None:
    cache_root = Path(os.environ.get("NEURO_RESEARCH_AGENT_CACHE", "/tmp/neuro_research_agent_cache"))
    matplotlib_cache = cache_root / "matplotlib"
    xdg_cache = cache_root / "xdg"
    fontconfig_cache = xdg_cache / "fontconfig"
    for path in (matplotlib_cache, xdg_cache, fontconfig_cache):
        path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="General neuroscience research agent inspired by AI-Researcher.")
    p.add_argument("--prompt", default="", help="User research prompt. If omitted in an interactive terminal, the script prompts for it.")
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--data-root", type=Path, default=None, help="Input data root. For current fMRI workflows this is the already processed fMRI output directory.")
    p.add_argument("--fmri-output-root", type=Path, default=None, help=argparse.SUPPRESS)
    p.add_argument("--raw-fmri-root", type=Path, default=None, help="Raw fMRI input root. If supplied, derivatives are checked before research analysis.")
    p.add_argument("--fmri-result-root", type=Path, default=None, help="fMRI preprocessing result root used by fmri_local_split.")
    p.add_argument("--processed-fmri-root", type=Path, default=None, help="Already processed fMRI root containing derivatives/.")
    p.add_argument("--fmri-local-agent-script", type=Path, default=Path("/home/qlp/Agent_skills/fmri_local_split/agent_skills/fmri-local-agent/scripts/fmri_local_agent.py"))
    p.add_argument("--subject", default="")
    p.add_argument("--session", default="")
    p.add_argument("--max-papers", type=int, default=20)
    p.add_argument("--max-code-results", "--max-code-resources", dest="max_code_results", type=int, default=10, help="Maximum code resources to retrieve per analysis route.")
    p.add_argument("--allow-network", action=argparse.BooleanOptionalAction, default=True, help="Enable live arXiv/Crossref/Semantic Scholar literature search and GitHub code search.")
    p.add_argument("--ollama-url", default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"), help="Ollama server URL used for interactive prompt parsing.")
    p.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", ""), help="Ollama model name for prompt parsing. Defaults to the first installed model.")
    p.add_argument("--no-run-experiments", action="store_true")
    p.add_argument("--yes", action="store_true", help="Skip interactive confirmation and run after parsing arguments.")
    return p


def prompt_task_text(current_prompt: str = "") -> str:
    if current_prompt:
        print(f"当前研究任务：{current_prompt}", flush=True)
    while True:
        answer = input("请输入新的研究任务：").strip()
        if answer:
            return answer
        print("研究任务不能为空。", flush=True)


def confirmed(answer: str) -> bool:
    return answer.strip().lower() in {"yes", "y", "是", "同意", "确认", "继续", "ok", "1"}


def declined(answer: str) -> bool:
    return answer.strip().lower() in {"no", "n", "否", "不同意", "取消", "返回", "重新输入", "0"}


def extract_prompt_path(prompt: str) -> Path | None:
    match = re.search(r"/[^\s，。；;、）)]+", prompt)
    if not match:
        return None
    raw = match.group(0).rstrip(".,，。；;:：")
    candidates = [raw]
    for marker in ["下的", "中的", "里的", "内的", "下", "中", "里", "内"]:
        idx = raw.find(marker)
        if idx > 0:
            candidates.append(raw[:idx].rstrip(".,，。；;:："))
    existing = [Path(candidate) for candidate in candidates if candidate and Path(candidate).exists()]
    if existing:
        return max(existing, key=lambda path: len(str(path)))
    return Path(candidates[-1] if candidates else raw)


def extract_prompt_paths(prompt: str) -> list[Path]:
    paths: list[Path] = []
    for match in re.finditer(r"/[^\s，。；;、）)]+", prompt):
        raw = match.group(0).rstrip(".,，。；;:：")
        candidates = [raw]
        for marker in ["下的", "中的", "里的", "内的", "下", "中", "里", "内"]:
            idx = raw.find(marker)
            if idx > 0:
                candidates.append(raw[:idx].rstrip(".,，。；;:："))
        existing = [Path(candidate) for candidate in candidates if candidate and Path(candidate).exists()]
        path = max(existing, key=lambda item: len(str(item))) if existing else Path(candidates[-1] if candidates else raw)
        if path not in paths:
            paths.append(path)
    return paths


def normalize_prompt_path(value: str | None) -> Path | None:
    if not value:
        return None
    raw = value.strip().strip("\"'").rstrip(".,，。；;:：")
    if not raw:
        return None
    candidates = [raw]
    for marker in ["下的", "中的", "里的", "内的", "下", "中", "里", "内"]:
        idx = raw.find(marker)
        if idx > 0:
            candidates.append(raw[:idx].rstrip(".,，。；;:："))
    path = Path(candidates[-1])
    existing = [Path(candidate) for candidate in candidates if candidate and Path(candidate).exists()]
    if existing:
        path = max(existing, key=lambda item: len(str(item)))
    elif raw.startswith("/"):
        for end in range(len(raw) - 1, 0, -1):
            prefix = raw[:end].rstrip(".,，。；;:：")
            if prefix and Path(prefix).exists():
                path = Path(prefix)
                break
    return path


def refine_raw_fmri_root_from_prompt(raw_root: Path | None, prompt: str) -> Path | None:
    if raw_root is None or not raw_root.exists() or not raw_root.is_dir():
        return raw_root
    children = [child for child in raw_root.iterdir() if child.is_dir() and not child.name.startswith(".")]
    if not children:
        return raw_root
    if raw_root.name in {"fmri_data", "data", "input"}:
        matches = [child for child in children if child.name in prompt]
        if matches:
            return max(matches, key=lambda path: len(path.name))
    return raw_root


def subject_from_raw_fmri_root(raw_root: Path | None) -> str | None:
    if raw_root is None:
        return None
    if raw_root.name.startswith("sub-"):
        return raw_root.name
    return None


def explicit_max_papers_from_prompt(prompt: str) -> int | None:
    patterns = [
        r"(?:最多|至多|不超过|检索|搜索|筛选|读取|参考)[^\d]{0,12}(\d{1,4})\s*(?:篇|个|条)?\s*(?:论文|文献|paper|papers)?",
        r"(\d{1,4})\s*(?:篇|个|条)\s*(?:论文|文献|paper|papers)",
        r"max(?:imum)?[_\s-]*papers?\D{0,8}(\d{1,4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.I)
        if match:
            value = int(match.group(1))
            return max(1, min(value, 1000))
    return None


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


def parse_prompt_with_ollama(prompt: str, base_url: str, configured_model: str) -> dict[str, Any]:
    model = ollama_model(base_url, configured_model)
    system_prompt = (
        "You are a strict JSON parser for a neuroscience research agent. "
        "Extract structured fields from the user's Chinese or English task. "
        "Return JSON only, no markdown, no explanations. "
        "Schema: {"
        "\"research_task\": string, "
        "\"data_root\": string|null, "
        "\"raw_fmri_input_root\": string|null, "
        "\"fmri_result_root\": string|null, "
        "\"processed_fmri_output_root\": string|null, "
        "\"data_root_kind\": \"processed_fmri_output\"|\"general_data\"|null, "
        "\"max_papers\": integer|null, "
        "\"subject\": null, "
        "\"session\": null"
        "}. "
        "raw_fmri_input_root is the raw input folder, for example a folder under fmri_data. "
        "fmri_result_root is the preprocessing result base folder, for example a folder under fmri_result. "
        "processed_fmri_output_root is an already processed folder containing derivatives, for example fmri_free. "
        "data_root should be the processed_fmri_output_root when available, otherwise null. "
        "If Chinese location words follow the path, such as 下的, 中的, 里的, 内的, do not include those words or later text in data_root. "
        "For this application, do not infer or fill subject/session from the prompt; always return null for subject and session."
    )
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": f"{system_prompt}\n\nUser task:\n{prompt}",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = parse_json_object(str(response.json().get("response", "")))
    payload["_parser"] = f"ollama:{model}"
    return payload


def parse_user_input(prompt: str, args: argparse.Namespace) -> dict[str, Any]:
    try:
        payload = parse_prompt_with_ollama(prompt, args.ollama_url, args.ollama_model)
    except Exception as exc:
        paths = extract_prompt_paths(prompt)
        raw_root = next((path for path in paths if "fmri_data" in path.parts), None)
        result_root = next((path for path in paths if "fmri_result" in path.parts and path.name not in {"fmri_free", "fmri_fast", "analysis_free", "analysis_fast"}), None)
        processed_root = next((path for path in paths if path.name in {"fmri_free", "fmri_fast", "analysis_free", "analysis_fast"} or (path / "derivatives").exists()), None)
        path = processed_root or extract_prompt_path(prompt)
        payload = {
            "research_task": prompt,
            "data_root": str(path) if path else None,
            "raw_fmri_input_root": str(raw_root) if raw_root else None,
            "fmri_result_root": str(result_root) if result_root else None,
            "processed_fmri_output_root": str(processed_root) if processed_root else None,
            "data_root_kind": "processed_fmri_output" if path else None,
            "subject": None,
            "session": None,
            "_parser": "fallback_path_extractor",
            "_parser_warning": str(exc),
        }
    payload["research_task"] = str(payload.get("research_task") or prompt).strip()
    path = normalize_prompt_path(payload.get("data_root"))
    payload["data_root"] = str(path) if path else None
    for key in ("raw_fmri_input_root", "fmri_result_root", "processed_fmri_output_root"):
        parsed_path = normalize_prompt_path(payload.get(key))
        payload[key] = str(parsed_path) if parsed_path else None
    prompt_paths = extract_prompt_paths(prompt)
    if not payload.get("raw_fmri_input_root"):
        raw_root = next((path for path in prompt_paths if "fmri_data" in path.parts), None)
        if raw_root:
            payload["raw_fmri_input_root"] = str(refine_raw_fmri_root_from_prompt(raw_root, prompt))
    else:
        refined_raw = refine_raw_fmri_root_from_prompt(Path(payload["raw_fmri_input_root"]), prompt)
        payload["raw_fmri_input_root"] = str(refined_raw) if refined_raw else payload["raw_fmri_input_root"]
    if not payload.get("fmri_result_root"):
        result_candidates = [
            path
            for path in prompt_paths
            if "fmri_result" in path.parts and path.name not in {"fmri_free", "fmri_fast", "analysis_free", "analysis_fast"}
        ]
        if result_candidates:
            payload["fmri_result_root"] = str(result_candidates[-1])
    if not payload.get("processed_fmri_output_root"):
        processed_root = next((path for path in prompt_paths if path.name in {"fmri_free", "fmri_fast", "analysis_free", "analysis_fast"} or (path / "derivatives").exists()), None)
        if processed_root:
            payload["processed_fmri_output_root"] = str(processed_root)
            payload["data_root"] = payload["data_root"] or str(processed_root)
    explicit_max_papers = explicit_max_papers_from_prompt(prompt)
    if explicit_max_papers is not None:
        payload["max_papers"] = explicit_max_papers
    return payload


def confirm_context(ctx: ResearchContext, allow_network: bool, assume_yes: bool, parsed_input: dict[str, Any]) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("当前不是交互终端；解析后确认需要交互输入。请加 --yes 明确确认后再运行。", file=sys.stderr, flush=True)
        return False

    print("\n已解析用户输入，请确认是否继续执行：", flush=True)
    print(f"  解析方式: {parsed_input.get('_parser', 'unknown')}", flush=True)
    if parsed_input.get("_parser_warning"):
        print(f"  解析提示: Ollama 解析不可用，已回退到路径抽取：{parsed_input['_parser_warning']}", flush=True)
    print(f"  研究任务: {ctx.prompt}", flush=True)
    print(f"  输出目录: {ctx.output_dir}", flush=True)
    print(f"  输入数据目录（已处理 fMRI 输出）: {ctx.data_root or '未指定'}", flush=True)
    print(f"  原始 fMRI 输入目录: {ctx.raw_fmri_input_root or '未指定'}", flush=True)
    print(f"  fMRI 预处理结果根目录: {ctx.fmri_result_root or '未指定'}", flush=True)
    print(f"  被试: {ctx.subject or '未指定'}", flush=True)
    print(f"  Session: {ctx.session or '未指定'}", flush=True)
    print(f"  最大论文数: {ctx.max_papers}", flush=True)
    print(f"  每个实验路线最大代码资源检索数: {ctx.max_code_results}", flush=True)
    print(f"  允许联网检索: {'是' if allow_network else '否'}", flush=True)
    print(f"  执行生成实验: {'是' if ctx.run_experiments else '否'}", flush=True)
    while True:
        answer = input("同意继续执行？输入 yes 继续，no 返回重新输入：").strip()
        if confirmed(answer):
            return True
        if declined(answer):
            return False
        print("请输入 yes 或 no。", flush=True)


def build_context(args: argparse.Namespace, output_dir: Path, prompt: str, parsed_input: dict[str, Any]) -> ResearchContext:
    parsed_root = normalize_prompt_path(parsed_input.get("data_root"))
    raw_fmri_root = args.raw_fmri_root or normalize_prompt_path(parsed_input.get("raw_fmri_input_root"))
    fmri_result_root = args.fmri_result_root or normalize_prompt_path(parsed_input.get("fmri_result_root"))
    parsed_processed_root = normalize_prompt_path(parsed_input.get("processed_fmri_output_root"))
    if parsed_processed_root is None and parsed_root is not None:
        if parsed_root.name in {"fmri_free", "fmri_fast", "analysis_free", "analysis_fast"} or (parsed_root / "derivatives").exists():
            parsed_processed_root = parsed_root
    processed_fmri_root = args.processed_fmri_root or args.data_root or args.fmri_output_root or parsed_processed_root
    input_root = processed_fmri_root
    return ResearchContext(
        prompt=str(parsed_input.get("research_task") or prompt),
        output_dir=output_dir,
        data_root=input_root,
        fmri_output_root=input_root,
        raw_fmri_input_root=raw_fmri_root,
        fmri_result_root=fmri_result_root,
        fmri_local_agent_script=args.fmri_local_agent_script,
        subject=args.subject or subject_from_raw_fmri_root(raw_fmri_root),
        session=args.session or None,
        max_papers=int(parsed_input.get("max_papers") or args.max_papers),
        max_code_results=args.max_code_results,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        run_experiments=not args.no_run_experiments,
    )


def main() -> int:
    configure_runtime_cache()
    args = parser().parse_args()
    if not args.prompt and not sys.stdin.isatty():
        print("非交互运行必须提供 --prompt。", file=sys.stderr, flush=True)
        return 2
    prompt = args.prompt.strip() or prompt_task_text()
    run_id = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or ROOT / "outputs" / run_id
    while True:
        parsed_input = parse_user_input(prompt, args)
        ctx = build_context(args, output_dir, prompt, parsed_input)
        if confirm_context(ctx, args.allow_network, args.yes, parsed_input):
            break
        if not sys.stdin.isatty():
            return 3
        prompt = prompt_task_text(prompt)
    progress_log("run", "entrypoint.run_neuroscience_research_agent", f"用户已确认，开始执行任务: {ctx.prompt}")
    from neuro_research_agent.workflows.research_flow import run_research_flow

    status = run_research_flow(ctx, allow_network=args.allow_network)
    progress_log("done", "entrypoint.run_neuroscience_research_agent", f"任务执行完成: output_dir={status['output_dir']}")
    print(status["output_dir"], flush=True)
    return int(status.get("returncode", 1))


if __name__ == "__main__":
    raise SystemExit(main())
