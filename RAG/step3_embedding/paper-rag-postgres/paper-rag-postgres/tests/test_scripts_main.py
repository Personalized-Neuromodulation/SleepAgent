import importlib.util
from pathlib import Path


def _load_main_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "main.py"
    spec = importlib.util.spec_from_file_location("paper_rag_script_main", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_passes_src_path_to_subprocess_pythonpath(monkeypatch):
    module = _load_main_module()
    captured = {}

    def fake_run(command, cwd=None, check=None, text=None, env=None):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.run(module.sys.executable, "-m", "paper_rag.cli", "status")

    assert captured["cwd"] == module.PROJECT_ROOT
    assert str(module.SRC_PATH) in captured["env"]["PYTHONPATH"].split(module.os.pathsep)
