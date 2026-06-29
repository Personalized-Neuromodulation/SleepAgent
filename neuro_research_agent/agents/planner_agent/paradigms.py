from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def load_paradigm_library() -> list[dict[str, Any]]:
    path = PACKAGE_ROOT / "resources" / "paradigm_library.json"
    return json.loads(path.read_text(encoding="utf-8"))


def score_prompt_match(prompt: str, paradigm: dict[str, Any]) -> int:
    lowered = prompt.lower()
    score = 0
    for keyword in paradigm.get("keywords", []):
        if keyword.lower() in lowered:
            score += 3
    prompt_tokens = set(re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", lowered))
    name_tokens = set(re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", (paradigm.get("name", "") + " " + paradigm.get("id", "")).lower()))
    score += len(prompt_tokens & name_tokens)
    return score


def classify_paradigms(prompt: str, available_types: set[str]) -> list[dict[str, Any]]:
    candidates = []
    for paradigm in load_paradigm_library():
        required = set(paradigm.get("required_data", []))
        missing = sorted(required - available_types)
        prompt_score = score_prompt_match(prompt, paradigm)
        data_score = 20 if not missing else max(0, 20 - len(missing) * 7)
        total = prompt_score + data_score
        candidates.append(
            {
                **paradigm,
                "prompt_match_score": prompt_score,
                "data_compatibility_score": data_score,
                "missing_data": missing,
                "executable": not missing,
                "selection_score": total,
            }
        )
    candidates.sort(key=lambda item: item["selection_score"], reverse=True)
    return candidates
