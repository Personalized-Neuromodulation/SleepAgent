#!/usr/bin/env bash
# Paper RAG launcher for Windows Git Bash + Conda environment "agent".
# Do not run this script with WSL's /bin/bash.

set -Eeuo pipefail

on_error() {
  local exit_code=$?
  echo "错误：脚本在第 ${BASH_LINENO[0]} 行失败，退出码 ${exit_code}。" >&2
  echo "容器日志命令：docker compose logs --tail=200" >&2
  exit "$exit_code"
}
trap on_error ERR

usage() {
  cat <<'EOF'
用法：./scripts/start.sh [模式]

模式：
  ingest    按 config.yaml 的 ingestion.limit 试导入（默认）
  full      全量导入，忽略 ingestion.limit
  api       启动 RAG API
  status    显示数据库语料状态
  services  显示 Docker 服务状态
  logs      持续显示 PostgreSQL/GROBID 日志
  stop      停止 PostgreSQL/GROBID
  help      显示帮助

环境：
  固定使用 Conda 环境：agent
  PAPER_RAG_CONFIG 可指定另一份 config.yaml
EOF
}

MODE="${1:-ingest}"
case "$MODE" in
  ingest|full|api|status|services|logs|stop) ;;
  help|-h|--help)
    usage
    exit 0
    ;;
  *)
    echo "错误：未知模式：$MODE" >&2
    usage >&2
    exit 2
    ;;
esac

SYSTEM_NAME="$(uname -s 2>/dev/null || true)"
case "$SYSTEM_NAME" in
  MINGW*|MSYS*|CYGWIN*) ;;
  Linux*)
    echo "错误：当前 bash 来自 WSL/Linux；本脚本要求 Windows Git Bash。" >&2
    echo "请从 PowerShell 明确调用 Git for Windows：" >&2
    echo '& "C:\Program Files\Git\bin\bash.exe" "D:/paper-rag-postgres/paper-rag-postgres/scripts/start.sh" ingest' >&2
    exit 2
    ;;
  *)
    echo "错误：当前环境不是 Windows Git Bash：$SYSTEM_NAME" >&2
    exit 2
    ;;
esac

if ! command -v cygpath >/dev/null 2>&1; then
  echo "错误：未找到 cygpath，请使用 Git for Windows 自带的 Git Bash。" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
PROJECT_DIR_WINDOWS="$(cygpath -w "$PROJECT_DIR")"
DEFAULT_CONFIG_WINDOWS="$(cygpath -w "$PROJECT_DIR/config.yaml")"
cd "$PROJECT_DIR"

export PAPER_RAG_CONFIG="${PAPER_RAG_CONFIG:-$DEFAULT_CONFIG_WINDOWS}"

if [[ ! -f config.yaml ]]; then
  echo "错误：找不到配置文件：${PROJECT_DIR_WINDOWS}\\config.yaml" >&2
  exit 1
fi

activate_agent_environment() {
  local conda_executable=""
  local conda_base_windows=""
  local conda_base_unix=""

  if [[ -n "${CONDA_EXE:-}" ]]; then
    if [[ "$CONDA_EXE" =~ ^[A-Za-z]:[\\/] ]]; then
      conda_executable="$(cygpath -u "$CONDA_EXE")"
    else
      conda_executable="$CONDA_EXE"
    fi
  elif command -v conda.exe >/dev/null 2>&1; then
    conda_executable="$(command -v conda.exe)"
  elif command -v conda >/dev/null 2>&1; then
    conda_executable="$(command -v conda)"
  else
    local candidate
    for candidate in \
      "/c/ProgramData/anaconda3/Scripts/conda.exe" \
      "/c/ProgramData/miniconda3/Scripts/conda.exe" \
      "$HOME/anaconda3/Scripts/conda.exe" \
      "$HOME/miniconda3/Scripts/conda.exe"; do
      if [[ -x "$candidate" ]]; then
        conda_executable="$candidate"
        break
      fi
    done
  fi

  if [[ -z "$conda_executable" ]]; then
    echo "错误：找不到 Conda。请在已安装 Conda 的 PowerShell 中调用本脚本。" >&2
    exit 1
  fi

  conda_base_windows="$("$conda_executable" info --base | tr -d '\r')"
  if [[ "$conda_base_windows" =~ ^[A-Za-z]:[\\/] ]]; then
    conda_base_unix="$(cygpath -u "$conda_base_windows")"
  else
    conda_base_unix="$conda_base_windows"
  fi

  if [[ ! -f "$conda_base_unix/etc/profile.d/conda.sh" ]]; then
    echo "错误：找不到 Conda 初始化脚本：$conda_base_unix/etc/profile.d/conda.sh" >&2
    exit 1
  fi

  # shellcheck disable=SC1091
  source "$conda_base_unix/etc/profile.d/conda.sh"
  conda activate agent

  if [[ "${CONDA_DEFAULT_ENV:-}" != "agent" ]]; then
    echo "错误：Conda 环境 agent 激活失败。" >&2
    exit 1
  fi
  python -c \
    'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else "agent环境需要Python 3.11或更高版本")'
  echo "已激活 Conda 环境：$CONDA_DEFAULT_ENV ($(python --version 2>&1))"
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "错误：未找到 docker，请安装并启动 Docker Desktop。" >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "错误：Docker Desktop 尚未启动，或当前用户无法连接 Docker。" >&2
    exit 1
  fi
}

start_services() {
  echo "[1/4] 启动 PostgreSQL 和 GROBID..."
  docker compose up -d postgres grobid

  echo "[2/4] 等待 PostgreSQL 就绪..."
  local attempt
  for attempt in $(seq 1 60); do
    if docker compose exec -T postgres pg_isready -U paper_rag -d paper_rag >/dev/null 2>&1; then
      break
    fi
    if [[ "$attempt" -eq 60 ]]; then
      echo "错误：PostgreSQL 在120秒内未就绪。" >&2
      docker compose logs --tail=100 postgres >&2
      exit 1
    fi
    sleep 2
  done

  echo "[3/4] 等待 GROBID 就绪..."
  for attempt in $(seq 1 90); do
    if curl --fail --silent --max-time 3 http://localhost:8070/api/isalive >/dev/null 2>&1; then
      return
    fi
    if [[ "$attempt" -eq 90 ]]; then
      echo "错误：GROBID 在180秒内未就绪。" >&2
      docker compose logs --tail=100 grobid >&2
      exit 1
    fi
    sleep 2
  done
}

prepare_project() {
  echo "[4/4] 在 Conda agent 环境安装/更新工程并初始化数据库..."
  python -m pip install -e .
  python -m paper_rag.cli init-db
}

require_docker

case "$MODE" in
  stop)
    docker compose stop postgres grobid
    exit 0
    ;;
  services)
    docker compose ps
    exit 0
    ;;
  logs)
    docker compose logs -f postgres grobid
    exit 0
    ;;
esac

activate_agent_environment

if [[ "$MODE" == "status" ]]; then
  python -m pip install -e .
  python -m paper_rag.cli status
  exit 0
fi

start_services
prepare_project

case "$MODE" in
  ingest)
    echo "开始试导入；数量由 config.yaml 的 ingestion.limit 控制。"
    python -m paper_rag.cli ingest
    python -m paper_rag.cli status
    ;;
  full)
    echo "开始全量导入。"
    python -m paper_rag.cli ingest --full
    python -m paper_rag.cli status
    ;;
  api)
    API_HOST="$(python -c 'from paper_rag.config import settings; print(settings.api_host)')"
    API_PORT="$(python -c 'from paper_rag.config import settings; print(settings.api_port)')"
    echo "启动 RAG API：http://localhost:${API_PORT}/docs"
    exec python -m uvicorn paper_rag.api:app --host "$API_HOST" --port "$API_PORT"
    ;;
esac
