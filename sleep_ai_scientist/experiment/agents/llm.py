from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.hypothesis.agents.llm import HypothesisLLMClient, LLMError, LLMResponse

try:  # pragma: no cover - optional templating dependency.
    from pybars import Compiler
except ModuleNotFoundError:  # pragma: no cover
    Compiler = None


_PROMPT_CACHE: dict[Path, dict[str, Any]] = {}


def experiment_llm_enabled(config: dict[str, Any]) -> bool:
    if "enabled" in config or "provider" in config or "model" in config:
        llm_cfg = config
    else:
        llm_cfg = config.get("llm", config.get("online", {}))
    return bool(llm_cfg.get("enabled", False))


class ExperimentLLMClient:
    """Experiment-facing wrapper around the shared Ollama/OpenAI-compatible client."""

    def __init__(self, config: dict[str, Any], *, task_name: str) -> None:
        self.task_name = task_name
        self.log_calls = bool(config.get("log_calls", True))
        llm_config = dict(config)
        llm_config["log_calls"] = False
        self.client = HypothesisLLMClient(llm_config)

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        self._log(messages, json_mode=json_mode)
        return self.client.call(messages, max_tokens=max_tokens, temperature=temperature, json_mode=json_mode)

    def call_json(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        self._log(messages, json_mode=True)
        return self.client.call_json(messages, max_tokens=max_tokens, temperature=temperature)

    def _log(self, messages: list[dict[str, str]], *, json_mode: bool) -> None:
        if not self.log_calls:
            return
        prompt_chars = sum(len(item.get("content", "")) for item in messages)
        print(
            "[experiment][llm] "
            f"task={self.task_name} "
            f"provider={self.client.provider} "
            f"model={self.client.model} "
            f"json={json_mode} "
            f"messages={len(messages)} "
            f"prompt_chars={prompt_chars}",
            flush=True,
        )


def build_experiment_llm(config: dict[str, Any], *, task_name: str = "experiment") -> ExperimentLLMClient | None:
    if not experiment_llm_enabled(config):
        return None
    return ExperimentLLMClient(config, task_name=task_name)


def load_prompt(category: str, name: str, variables: dict[str, Any] | None = None) -> tuple[str, str, int]:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / category / f"{name}.yaml"
    if prompt_path not in _PROMPT_CACHE:
        _PROMPT_CACHE[prompt_path] = read_yaml(prompt_path)
    payload = _PROMPT_CACHE[prompt_path]
    variables = variables or {}
    system = _render_template(str(payload.get("system", "")), variables)
    user = _render_template(str(payload.get("user", "")), variables)
    return system, user, int(payload.get("max_tokens", 4096))


def _render_template(template: str, variables: dict[str, Any]) -> str:
    if Compiler is not None:
        return Compiler().compile(template)(variables)

    def replace_if(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        body = match.group(2)
        return body if variables.get(key) else ""

    rendered = re.sub(r"{{#if\s+([^}]+)}}([\s\S]*?){{/if}}", replace_if, template)
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


__all__ = ["ExperimentLLMClient", "LLMError", "build_experiment_llm", "experiment_llm_enabled", "load_prompt"]
