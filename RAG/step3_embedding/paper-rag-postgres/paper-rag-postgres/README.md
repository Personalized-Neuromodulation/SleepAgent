# Paper RAG PostgreSQL

面向已经下载到磁盘的科研论文语料库：读取 `download_results.csv`，校验 PDF/XML/JSON/Markdown，按 `PDF > XML > JSON > MD` 选择同一论文的最佳全文，解析为统一结构，按章节分层切块，写入 PostgreSQL，并提供 pgvector + 全文检索的混合搜索与带来源的 RAG API。

## 数据保存边界

| 数据 | 保存位置 | 说明 |
|---|---|---|
| 原始 PDF/XML/JSON/MD | 原论文目录 | 数据库只保存路径、真实格式、大小和 SHA256，不重复塞入大文件 |
| 统一解析结果 | `PAPER_RAG_CANONICAL_ROOT` | 每个文档一份可重建的 JSON，便于审计和重新入库 |
| 论文元数据与摘要 | PostgreSQL `papers` | DOI 优先去重；无 DOI 时按标题+期刊匹配 |
| 文件及解析状态 | `documents`、`document_versions` | 一个文件可有多个解析版本；SHA256 用于文件级去重 |
| 正文章节 | `sections` | 统一的标题、类型、顺序、页码、正文 |
| 父块与子块 | `chunks` | 父块用于返回上下文，子块用于精确检索 |
| 向量 | `paper_embeddings`、`chunk_embeddings` | Title+Abstract 为论文级向量；子块、图注、表注为检索向量 |

`documents` 并不保存原始文件二进制。`original_path` 指向磁盘文件，`file_sha256` 是整个原始文件字节的哈希；`canonical_path` 指向规范化 JSON。数据库保存可查询的正文，而原文件仍是事实来源。

## 处理流程

1. 读取 CSV，只处理 `status=success`。
2. 检查 `file` 是否存在，根据文件内容判断真实 PDF/XML/JSON/Markdown，而不是只信扩展名；普通 TXT 明确拒绝。
3. 按 DOI 归并同一篇论文；没有 DOI 时按规范化标题+期刊归并。存在多个全文时只选择 `PDF > XML > JSON > MD` 中最高优先级且实际可用的文件。
4. 对选中的整个原始文件计算 SHA256，创建/更新 `Paper` 和 `Document`。
5. PDF 优先送 GROBID 生成 TEI，失败时使用 PyMuPDF；XML 识别 TEI/JATS；JSON 支持统一章节结构或常见全文字段；Markdown 按标题层级恢复章节。
6. 输出统一结构，保存摘要、章节、参考文献、图表注，并记录解析器版本和质量告警。
7. 每个章节生成约 1200 token 父块、550 token 子块（80 token 重叠）。
8. `Title + Abstract` 生成论文级向量；子块及图表注生成块级向量。
9. 用 pgvector 余弦近邻与 PostgreSQL `tsvector` 全文搜索召回，再用 RRF 融合；回答时扩展为父块上下文。

导入是幂等的：同一文件 SHA256 且已经完成向量化时会跳过；解析器或切块规则升级后可使用 `--force` 重建。如果数据库中已有低优先级版本，后来导入更高优先级版本，旧版本仍保留用于审计，但只有新版本处于活动状态并参与检索。

## 快速开始（Windows）

要求：Python 3.11+、Docker Desktop。主要配置集中在项目根目录的 `config.yaml`。GPU 非必需；没有 CUDA 时把 `embedding.device` 改为 `cpu`。

这是 Windows 工程，`scripts/start.sh` 必须使用 **Git for Windows 自带的 Git Bash**，不能使用 WSL 的 `/bin/bash`。脚本固定激活已有的 Conda 环境 `agent`，不创建 `.venv`。

直接打开 Git Bash，然后执行：

```bash
cd paper-rag-postgres
chmod +x scripts/start.sh
./scripts/start.sh ingest
```

也可以从 PowerShell 明确调用 Git Bash。不要直接执行 `bash ...`，因为 Windows 可能把它解析成 WSL：

```powershell
& "C:\Program Files\Git\bin\bash.exe" "D:/paper-rag-postgres/paper-rag-postgres/scripts/start.sh" ingest
```

脚本会自动定位 Conda、执行 `conda activate agent`、启动 PostgreSQL/GROBID、在 `agent` 环境安装工程、初始化数据库、按照 `config.yaml` 导入论文并显示状态。

先编辑 `config.yaml`，至少确认：

```yaml
paths:
  paper_root: 'D:\crawler2025\crawler_light\exports_811\sleep'
  canonical_root: 'D:\crawler2025\crawler_light\exports_811\sleep_rag_canonical'
  source_csv: 'D:\crawler2025\crawler_light\download_results.csv'
embedding:
  device: 'cuda'
ingestion:
  limit: 20
```

启动脚本支持以下模式：

```bash
./scripts/start.sh ingest    # 按config.yaml的limit试运行
./scripts/start.sh full      # 忽略limit，全量导入
./scripts/start.sh api       # 启动RAG API
./scripts/start.sh services  # 查看PostgreSQL/GROBID容器状态
./scripts/start.sh status    # 查看数据库语料状态
./scripts/start.sh logs      # 查看容器实时日志
./scripts/start.sh stop      # 停止服务
```

也可以不使用脚本，手动执行命令：

```powershell
docker compose up -d postgres grobid
conda activate agent
pip install -e .
paper-rag init-db
paper-rag ingest
paper-rag status
```

命令行参数可以临时覆盖 YAML，例如 `paper-rag ingest --csv "..." --limit 50`，全量导入使用 `paper-rag ingest --full`。环境变量也可以覆盖配置，例如 `PAPER_RAG_EMBEDDING_DEVICE=cpu`。通过 `PAPER_RAG_CONFIG` 可以指定另一份 YAML。

脚本会拒绝 WSL，确保使用 Conda `agent` 中的 Windows Python 和 `D:\...` 路径。

首次运行会下载 `BAAI/bge-m3`。默认数据库向量列固定为 1024 维，因此更换 Embedding 模型时，必须同时修改 `config.yaml` 和 `db/init.sql` 中的 `vector(1024)`，然后迁移或重建向量表。

## RAG 服务

默认调用 Ollama 的 OpenAI 兼容接口：

```bash
ollama pull qwen3:14b
./scripts/start.sh api
```

检索：

```powershell
curl -X POST http://localhost:8000/search `
  -H "Content-Type: application/json" `
  -d '{"query":"sleep and dementia risk","top_k":8,"expand_parent":true}'
```

问答：

```powershell
curl -X POST http://localhost:8000/rag `
  -H "Content-Type: application/json" `
  -d '{"question":"睡眠时长与痴呆风险有什么关系？","top_k":8}'
```

如果使用其他 OpenAI 兼容服务，修改 `config.yaml` 的 `llm` 部分即可；也能使用 `PAPER_RAG_LLM_BASE_URL`、`PAPER_RAG_LLM_API_KEY` 和 `PAPER_RAG_LLM_MODEL` 覆盖。返回结构包含答案与完整来源列表，不只依赖模型生成的引用文本。

## 核心表

- `papers`：论文实体。DOI、题名、摘要、期刊和源 CSV 元数据。
- `documents`：磁盘文件实体。路径、真实格式、SHA256、解析状态和告警。
- `document_versions`：统一全文的可追溯解析版本。
- `sections`：摘要之外的标准章节正文。
- `chunks`：父/子块、章节语义、页码、切块规则版本和全文索引。
- `paper_embeddings`：Title+Abstract 向量。
- `chunk_embeddings`：子块及图表说明向量。

原文不会因 CSV 文件名变化而被重复写入：SHA256 识别内容相同的文件。路径是定位信息，哈希是内容身份。若原文件被移动，可更新 `documents.original_path`/`relative_path`，无需重新生成向量；若哈希改变，则应创建新文档或新解析版本。

## 解析质量策略

- GROBID 成功：保留章节层级、摘要、参考文献和部分图表说明，质量通常最高。
- PDF 回退解析：可得到页码和文本，但双栏顺序、公式、表格结构可能不准确，系统会记录 warning。
- JATS/TEI XML：优先使用结构化标签，通常比 PDF 更可靠。
- JSON：支持 `title`、`abstract`、`sections`、`full_text`、`figures`、`tables`、`references` 等字段；只有元数据而没有足够全文时拒绝入库。
- Markdown：按 `#`～`######` 标题恢复结构，清理链接、图片标记和代码块；通常没有可靠页码。
- 普通 TXT 不解析；HTML 错误页和机器人验证页即使伪装成受支持后缀，也会在真实格式验证阶段被拒绝。

建议先抽样审查 50–100 篇的 `canonical JSON`、章节数、文本长度和告警，再全量向量化。扫描 PDF 需要额外接入 OCR；本项目会把无可提取文本的 PDF 标记为解析失败，不会把空内容写入 RAG。

## 开发验证

```powershell
pip install -e ".[dev]"
pytest
ruff check .
python -m compileall src
```

数据库初始化 SQL 位于 `db/init.sql`。生产环境请更换默认密码、固定镜像版本、备份 PostgreSQL，并将原论文目录设置为只读。
