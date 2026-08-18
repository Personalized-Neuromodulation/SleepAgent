from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
REQUIRED_SERVICES = ("postgres", "grobid")


def run(*command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", subprocess.list2cmdline(command), flush=True)
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=check,
        text=True,
    )


def require_agent_environment() -> None:
    environment = os.environ.get("CONDA_DEFAULT_ENV", "")
    if environment != "agent":
        raise SystemExit(
            "当前没有激活Conda环境agent。请先执行：conda activate agent"
        )
    if sys.version_info < (3, 11):
        raise SystemExit("Conda环境agent需要Python 3.11或更高版本")
    print(f"Conda环境：{environment} | Python：{sys.version.split()[0]}")


def require_docker() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("找不到docker命令，请安装并启动Docker Desktop")
    result = subprocess.run(
        ["docker", "info"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise SystemExit("Docker Desktop尚未启动，或当前用户无法连接Docker Engine")


def wait_for_postgres(timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                "docker", "compose", "exec", "-T", "postgres",
                "pg_isready", "-U", "paper_rag", "-d", "paper_rag",
            ],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
        time.sleep(2)
    raise SystemExit("PostgreSQL在120秒内没有就绪，请运行：docker compose logs postgres")


def wait_for_grobid(timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            with opener.open("http://127.0.0.1:8070/api/isalive", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(2)
    raise SystemExit("GROBID在180秒内没有就绪，请运行：docker compose logs grobid")


def running_services() -> set[str]:
    result = subprocess.run(
        ["docker", "compose", "ps", "--services", "--filter", "status=running"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.split()) if result.returncode == 0 else set()


def ensure_services(required: tuple[str, ...]) -> None:
    """Start only missing services; already-running containers are left untouched."""
    require_docker()
    missing = [service for service in required if service not in running_services()]
    if missing:
        print("启动尚未运行的服务：" + ", ".join(missing))
        run("docker", "compose", "up", "-d", *missing)
    else:
        print("所需Docker服务已经运行，不重复启动")
    if "postgres" in required:
        wait_for_postgres()
    if "grobid" in required:
        wait_for_grobid()
    print("所需服务已就绪")


def paper_rag(*arguments: str) -> None:
    run(sys.executable, "-m", "paper_rag.cli", *arguments)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paper RAG Windows入口")
    parser.add_argument(
        "mode",
        nargs="?",
        default="ingest",
        choices=("ingest", "full", "api", "status", "services", "logs", "stop", "up"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    os.chdir(PROJECT_ROOT)
    os.environ.setdefault("PAPER_RAG_CONFIG", str(CONFIG_PATH))

    if args.mode in {"services", "logs", "stop"}:
        require_docker()
        if args.mode == "services":
            run("docker", "compose", "ps")
        elif args.mode == "logs":
            run("docker", "compose", "logs", "-f", *REQUIRED_SERVICES)
        else:
            run("docker", "compose", "stop", *REQUIRED_SERVICES)
        return

    require_agent_environment()
    required = (
        REQUIRED_SERVICES
        if args.mode in {"ingest", "full", "up"}
        else ("postgres",)
    )
    ensure_services(required)
    if args.mode == "up":
        return
    
    paper_rag("init-db")

    if args.mode == "ingest":
        paper_rag("ingest")
        paper_rag("status")
    elif args.mode == "full":
        paper_rag("ingest", "--full")
        paper_rag("status")
    elif args.mode == "status":
        paper_rag("status")
    elif args.mode == "api":
        host = subprocess.check_output(
            [sys.executable, "-c", "from paper_rag.config import settings; print(settings.api_host)"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
        port = subprocess.check_output(
            [sys.executable, "-c", "from paper_rag.config import settings; print(settings.api_port)"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
        run(
            sys.executable,
            "-m",
            "uvicorn",
            "paper_rag.api:app",
            "--host",
            host,
            "--port",
            port,
        )


if __name__ == "__main__":
    main()
