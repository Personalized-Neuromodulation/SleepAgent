from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_yaml

try:  # pragma: no cover - optional dependency path.
    from json_repair import repair_json
except ModuleNotFoundError:  # pragma: no cover
    repair_json = None

try:  # pragma: no cover - optional dependency path.
    from pybars import Compiler
except ModuleNotFoundError:  # pragma: no cover
    Compiler = None


class LLMError(RuntimeError):
    pass


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    content: str
    usage: LLMUsage


_TOTAL_TOKENS_USED = 0
_DELTA_BASELINE = 0
_PROMPT_CACHE: dict[Path, dict[str, Any]] = {}


def _estimate_tokens(messages: list[dict[str, str]], response: str = "") -> LLMUsage:
    prompt_chars = sum(len(item.get("content", "")) for item in messages)
    completion_chars = len(response)
    prompt_tokens = max(1, prompt_chars // 4)
    completion_tokens = max(1, completion_chars // 4) if response else 0
    return LLMUsage(prompt_tokens, completion_tokens, prompt_tokens + completion_tokens)


def _add_usage(usage: LLMUsage) -> None:
    global _TOTAL_TOKENS_USED
    _TOTAL_TOKENS_USED += usage.total_tokens


def get_total_tokens_used() -> int:
    return _TOTAL_TOKENS_USED


def get_tokens_delta() -> int:
    global _DELTA_BASELINE
    delta = _TOTAL_TOKENS_USED - _DELTA_BASELINE
    _DELTA_BASELINE = _TOTAL_TOKENS_USED
    return delta


def _strip_think(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", text or "", flags=re.IGNORECASE).strip()


def _render_template(template: str, variables: dict[str, Any]) -> str:
    if Compiler is not None:
        compiler = Compiler()
        return compiler.compile(template)(variables)

    def replace_if(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        body = match.group(2)
        return body if variables.get(key) else ""

    rendered = re.sub(r"{{#if\s+([^}]+)}}([\s\S]*?){{/if}}", replace_if, template)
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def load_prompt(category: str, name: str, variables: dict[str, Any] | None = None) -> tuple[str, str, int]:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / category / f"{name}.yaml"
    if prompt_path not in _PROMPT_CACHE:
        _PROMPT_CACHE[prompt_path] = read_yaml(prompt_path)
    payload = _PROMPT_CACHE[prompt_path]
    variables = variables or {}
    system = _render_template(str(payload.get("system", "")), variables)
    user = _render_template(str(payload.get("user", "")), variables)
    return system, user, int(payload.get("max_tokens", 8192))


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = _strip_think(text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    try:
                        parsed = json.loads(candidate)
                        return parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        if repair_json is not None:
                            try:
                                repaired = json.loads(repair_json(candidate))
                                return repaired if isinstance(repaired, dict) else None
                            except (json.JSONDecodeError, ValueError):
                                pass
                    return None

    if repair_json is not None:
        try:
            repaired = json.loads(repair_json(text))
            return repaired if isinstance(repaired, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None


class HypothesisLLMClient:
    """OpenAI-compatible chat client with Ollama local-provider support."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = normalize_llm_config(config)
        self.provider = str(self.config.get("provider", "ollama")).lower()
        self.model = str(self.config.get("model", "")).strip()
        if not self.model:
            raise LLMError("Missing LLM model name")

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        if bool(self.config.get("log_calls", True)):
            prompt_chars = sum(len(item.get("content", "")) for item in messages)
            print(
                f"[hypothesis][llm] provider={self.provider} model={self.model} json={json_mode} messages={len(messages)} prompt_chars={prompt_chars}",
                flush=True,
            )
        if self.provider in {"online", "deepseek", "openai_compatible"}:
            return self._call_openai_compatible(messages, max_tokens=max_tokens, temperature=temperature, json_mode=json_mode)
        if self.provider == "ollama":
            return self._call_ollama(messages, temperature=temperature, json_mode=json_mode)
        raise LLMError(f"Unsupported LLM provider: {self.provider}")

    def call_multi_turn(
        self,
        system: str,
        turns: list[dict[str, str]],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        return self.call([{"role": "system", "content": system}, *turns], max_tokens=max_tokens, temperature=temperature, json_mode=json_mode)

    def call_json(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        response = self.call(messages, max_tokens=max_tokens, temperature=temperature, json_mode=True)
        parsed = extract_json_object(response.content)
        if parsed is not None:
            return parsed

        retry_messages = [
            {"role": "system", "content": "You are a JSON formatter. Output only valid JSON with no markdown."},
            {
                "role": "user",
                "content": "Extract and return only the JSON object from this malformed response:\n\n"
                + response.content[:4000],
            },
        ]
        retry = self.call(retry_messages, max_tokens=max_tokens, temperature=0.0, json_mode=True)
        parsed = extract_json_object(retry.content)
        if parsed is not None:
            return parsed

        retry2 = self.call(
            messages
            + [
                {"role": "assistant", "content": response.content[:4000]},
                {"role": "user", "content": "Regenerate the answer as only the requested JSON object."},
            ],
            max_tokens=max_tokens,
            temperature=0.0,
            json_mode=True,
        )
        parsed = extract_json_object(retry2.content)
        if parsed is None:
            raise LLMError("LLM JSON extraction failed after two retries")
        return parsed

    def _call_openai_compatible(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float | None,
        json_mode: bool,
    ) -> LLMResponse:
        try:
            from openai import OpenAI
        except ModuleNotFoundError:
            return self._call_openai_compatible_http(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
            )

        client = OpenAI(
            base_url=str(self.config.get("base_url", "https://api.deepseek.com")),
            api_key=str(self.config.get("api_key", "")),
        )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        last_error: Exception | None = None
        for attempt in range(int(self.config.get("max_retries", 3))):
            try:
                completion = client.chat.completions.create(**body)
                usage = LLMUsage(
                    prompt_tokens=completion.usage.prompt_tokens if completion.usage else 0,
                    completion_tokens=completion.usage.completion_tokens if completion.usage else 0,
                    total_tokens=completion.usage.total_tokens if completion.usage else 0,
                )
                content = _strip_think(completion.choices[0].message.content or "")
                _add_usage(usage)
                return LLMResponse(content=content, usage=usage)
            except Exception as exc:  # pragma: no cover - network path.
                last_error = exc
                if getattr(exc, "status_code", None) == 401:
                    raise
                time.sleep(2**attempt)
        raise LLMError(f"OpenAI-compatible LLM call failed: {last_error}")

    def _call_openai_compatible_http(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float | None,
        json_mode: bool,
    ) -> LLMResponse:
        api_key = str(self.config.get("api_key", ""))
        if not api_key:
            raise LLMError("Missing API key for online OpenAI-compatible provider")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        base_url = str(self.config.get("base_url", "https://api.deepseek.com")).rstrip("/")
        url = f"{base_url}/chat/completions"
        last_error: Exception | None = None
        for attempt in range(int(self.config.get("max_retries", 3))):
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=float(self.config.get("timeout", 120))) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                usage_payload = payload.get("usage", {}) if isinstance(payload, dict) else {}
                usage = LLMUsage(
                    prompt_tokens=int(usage_payload.get("prompt_tokens", 0) or 0),
                    completion_tokens=int(usage_payload.get("completion_tokens", 0) or 0),
                    total_tokens=int(usage_payload.get("total_tokens", 0) or 0),
                )
                content = _strip_think(str(payload["choices"][0]["message"].get("content", "")))
                if usage.total_tokens == 0:
                    usage = _estimate_tokens(messages, content)
                _add_usage(usage)
                return LLMResponse(content=content, usage=usage)
            except urllib.error.HTTPError as exc:  # pragma: no cover - network path.
                last_error = exc
                if exc.code == 401:
                    detail = exc.read().decode("utf-8", errors="replace")
                    raise LLMError(f"OpenAI-compatible provider authentication failed: {detail}") from exc
                time.sleep(2**attempt)
            except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = exc
                time.sleep(2**attempt)
        raise LLMError(f"OpenAI-compatible HTTP call failed: {last_error}")

    def _call_ollama(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None,
        json_mode: bool,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature if temperature is not None else float(self.config.get("temperature", 0.2))},
        }
        if json_mode:
            payload["format"] = "json"
        request = urllib.request.Request(
            f"{str(self.config.get('base_url', 'http://localhost:11434')).rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.config.get("timeout", 120))) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError("Ollama returned a non-JSON transport response") from exc
        content = _strip_think(str(body.get("message", {}).get("content", "")))
        usage = _estimate_tokens(messages, content)
        _add_usage(usage)
        return LLMResponse(content=content, usage=usage)


def normalize_llm_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    if "provider" in config:
        normalized = dict(config)
        if str(normalized.get("provider", "")).lower() == "deepseek":
            normalized["provider"] = "online"
        api_key = str(normalized.get("api_key", ""))
        env_match = re.fullmatch(r"\$\{([^}]+)\}", api_key)
        if env_match:
            normalized["api_key"] = os.environ.get(env_match.group(1), "")
        normalized.setdefault("enabled", False)
        normalized.setdefault("temperature", 0.2)
        if str(normalized.get("provider", "")).lower() == "ollama":
            normalized.setdefault("base_url", "http://localhost:11434")
            normalized.setdefault("timeout", 120)
        else:
            normalized.setdefault("base_url", "https://api.deepseek.com")
            normalized.setdefault("model", "deepseek-chat")
            normalized.setdefault("max_retries", 3)
            normalized.setdefault("disable_thinking", True)
        return normalized
    # Backward compatibility with the previous `ollama:` config block.
    return {
        "enabled": config.get("enabled", False),
        "provider": "ollama",
        "base_url": config.get("base_url", "http://localhost:11434"),
        "model": config.get("model", ""),
        "timeout": config.get("timeout", 120),
        "temperature": config.get("temperature", 0.2),
        "fallback_to_rules": config.get("fallback_to_rules", False),
        "debate_rating_threshold": config.get("debate_rating_threshold", 1400),
    }


def llm_enabled(config: dict[str, Any] | None) -> bool:
    return bool(normalize_llm_config(config).get("enabled", False))


def build_llm_client(config: dict[str, Any] | None) -> HypothesisLLMClient:
    return HypothesisLLMClient(normalize_llm_config(config))
