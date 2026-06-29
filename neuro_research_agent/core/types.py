from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class AgentResult:
    value: Any = None
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]


@dataclass
class ResearchContext:
    prompt: str
    output_dir: Path
    data_root: Path | None = None
    fmri_output_root: Path | None = None
    raw_fmri_input_root: Path | None = None
    fmri_result_root: Path | None = None
    fmri_local_agent_script: Path | None = None
    subject: str | None = None
    session: str | None = None
    max_papers: int = 20
    max_code_results: int = 10
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = ""
    run_experiments: bool = True
