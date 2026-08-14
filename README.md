# TraceFlow — 可观测 Agent 工作流框架

面向知识库问答的单 Agent 工作流框架。以工具路由、执行追踪、回放对比和自动评测为核心，通过 MCP 协议对接检索后端，为 LLM 应用提供可解释、可复现、可评测的 Agent 基础设施。

## 功能特性

- 通过 `ToolRegistry` 统一管理工具，内置 `search_knowledge_base` 和 `get_corpus_stats`，支持热插拔。
- 单 Agent 确定性路由：基于中英文关键词判断调用检索或统计工具，无需 LLM 参与路由决策，结果可复现。
- 工具执行失败自动重试，每次 attempt 记录在 trace 中，支持定位间歇性故障。
- **双层 Trace 追踪**：Agent 层 trace 记录工具调用步骤、参数、结果和重试；MCP 模式下嵌套后端检索诊断（HyDE 状态、RRF 融合分数、rerank 分数、各阶段耗时）。
- 每次 run 生成唯一 `run_id`，持久化为 JSONL，支持按 `run_id` 回放并对比两次运行的工具路径一致性、来源重合度（Jaccard）和 token/cost 变化。
- **MCP 协议集成**：通过 StreamableHTTP 传输层对接检索后端，工具发现和调用走标准 MCP 协议，客户端零硬编码。
- 答案生成支持 DeepSeek / OpenAI / 任意 OpenAI 兼容 API，自动识别 provider；模型调用失败时回退本地摘录式回答，trace 记录错误步骤。
- 本地模式使用纯 Python 实现的 BM25 + 字符 n-gram TF-IDF 混合检索，零向量库依赖，返回每个 chunk 的原始分数、归一化分数和融合权重。
- Token 用量统计和成本估算，支持多模型定价表。
- 自动评测框架：eval cases 驱动的工具选择验证、关键词命中检查、来源命中检查，输出 pass rate 和延迟报告。
- FastAPI 托管 Web 控制台，支持提问、查看答案、sources、trace、usage 和最近运行，中英文界面切换。

## 技术栈

### Agent 工作流

| 环节 | 技术选型 | 设计要点 |
|---|---|---|
| 工具管理 | `ToolRegistry` 模式 | 统一注册、命名、执行入口；工具失败捕获异常转为 `ToolResult.error`，不中断 Agent 流程；支持本地和 MCP 两种 registry 实现 |
| 路由策略 | 确定性关键词路由 | 中英文关键词匹配（stats/统计/how many/多少等），无需 LLM 参与路由，结果可复现，延迟可控；后续可扩展为 LLM function calling |
| 重试机制 | attempt 级记录 | 每次工具调用（含失败）记录为独立 attempt，写入 trace；`max_tool_retries` 可配置，最后一次成功结果作为最终输出 |
| 答案生成 | OpenAI 兼容接口 | 支持 DeepSeek/OpenAI/任意兼容 API；通过 `base_url` 和 `model` 自动推断 provider；系统提示词约束只基于检索片段回答并引用 chunk_id |
| 降级容错 | 本地摘录回退 | 模型调用失败时不崩溃：回退到基于检索证据的摘录式回答，trace 记录 `answer_generator` 错误步骤，前端仍可查看 sources/trace/usage |

### 检索引擎

| 环节 | 技术选型 | 设计要点 |
|---|---|---|
| 本地检索 | BM25 + 字符 n-gram TF-IDF | 纯 Python 标准库实现，零外部依赖；BM25 处理精确词项、缩写和代码类查询，n-gram TF-IDF 处理中文局部字符串匹配和拼写变化；返回 raw/norm/fused 三级分数 |
| 混合融合 | 加权线性融合 | BM25 权重 0.65 + 向量权重 0.35；max 归一化消除量纲差异；每个 chunk 返回 `score_details` 记录两路原始分数和融合权重，便于解释召回原因 |
| MCP 远程检索 | StreamableHTTP 传输 | 对接 TraceRAG 后端：bge-m3 向量检索 + BM25 加权 RRF 融合 + HyDE 查询改写 + bge-reranker CrossEncoder 精排；检索 trace 嵌套在 Agent trace 中返回 |
| 文件加载 | PyMuPDF + 递归窗口 | 支持 `.txt .md .py .json .csv .log .pdf`；基于段落、换行、中文句号的智能切分，保留 `chunk_id`/`char_start`/`char_end` 元数据 |

### 可观测性

| 环节 | 技术选型 | 设计要点 |
|---|---|---|
| Trace 持久化 | append-only JSONL | 每次 run 追加一条记录，含 `run_id`/`query`/`answer`/`trace`/`sources`/`usage`/`created_at`；append-only 保证写入不阻塞读，便于离线分析 |
| 回放对比 | run_id 级 replay | 按 `run_id` 取历史请求重跑，自动对比工具路径一致性、来源 Jaccard 重合度、token/cost delta；用于验证配置变更或模型升级的影响 |
| 成本核算 | 多模型定价表 | 本地模式按字符估算 token（ASCII ÷ 4 + 非 ASCII ÷ 2），模型模式读取 API 返回的真实 usage；按模型名查定价表估算 USD 成本 |
| 调用链 | 结构化 trace dict | 每步记录 step 序号、tool 名、arguments、result（含 attempts）；MCP 模式下 result.output 嵌套 `retrieval_trace`（HyDE/RRF/rerank/timing） |

### 评测框架

| 环节 | 技术选型 | 设计要点 |
|---|---|---|
| Eval 驱动 | JSONL cases | 每条 case 含 question、expected_tool、expected_keywords、expected_sources；Agent 真实 run 后检查工具选择、关键词命中、来源命中 |
| 评测报告 | pass rate + 延迟 | 输出每条 case 的 passed/tool_hit/keyword_hit/source_hit/latency_ms/usage，汇总 pass_rate/avg_latency/total_usage；支持写入 JSON 报告 |
| 本地确定性 | `--local-only` | 禁用外部模型调用，保证 CI 环境下评测结果可复现 |

### 服务与前端

| 环节 | 技术选型 | 设计要点 |
|---|---|---|
| API 服务 | FastAPI + Uvicorn | lifespan 管理单例 Agent，请求复用内存中的 registry/generator/trace_store；Pydantic 校验请求体 |
| Web 控制台 | 原生 HTML/CSS/JS | 无框架依赖，无构建步骤；FastAPI `StaticFiles` 托管 `/assets`，`/` 返回 `index.html` |
| 前后端通信 | fetch + JSON | `/agent` POST 发送 query，返回 answer/trace/sources/usage/run_id；`/traces` GET 拉取最近运行；`/stats` GET 拉取运行时状态 |
| 国际化 | 运行时切换 | localStorage 持久化语言偏好；`data-i18n` 属性 + `messages` 字典实现中英文切换，无 i18n 库依赖 |

### MCP 协议层

| 环节 | 技术选型 | 设计要点 |
|---|---|---|
| 传输层 | StreamableHTTP | MCP 官方 Python SDK（`mcp>=2.0`）；后端 `MCPServer.streamable_http_app()` 挂载为 ASGI 子应用，复用 FastAPI 进程；客户端 `streamable_http_client` 建立会话 |
| Server 实现 | `MCPServer` + `@tool()` | 装饰器注册工具，自动生成 JSON Schema；工具函数同步执行（reranker 是 CPU 密集型），MCP runtime 在 worker thread 调度 |
| Client 实现 | 无状态会话 | 每次 `call_tool` 独立建立 session → initialize → call_tool → close；`asyncio.run` 桥接同步 `ToolRegistry`；ExceptionGroup 自动解包为可读错误信息 |
| 工具映射 | 名称对齐 | MCP 工具名（`rag_search` → `search_knowledge_base`）与本地 registry 一致，`SingleAgent` 路由逻辑零改动；`build_mcp_registry` 封装远程工具为 `ToolSpec` |

## 系统架构

```text
用户 query
  -> SingleAgent 确定性路由（关键词判断）
  -> ToolRegistry 执行工具（失败自动重试）
  │
  ├── 本地模式: BM25 + n-gram TF-IDF 混合检索
  └── MCP 模式: StreamableHTTP -> TraceRAG 后端
                 -> bge-m3 向量检索 + BM25 -> RRF 融合
                 -> HyDE 假想文档查询改写
                 -> bge-reranker CrossEncoder 精排
                 -> 代码查询邻居扩展
  -> AnswerGenerator 答案生成（模型失败回退本地摘录）
  -> TraceStore JSONL 持久化
  -> answer + trace + sources + usage + run_id
```

## 目录结构

```text
src/
  agent.py           单 Agent 工作流（路由、执行、重试、trace 组装）
  tools.py           ToolRegistry + 本地工具 + MCP registry 构建器
  mcp_client.py      MCP StreamableHTTP 客户端（无状态会话 + 异常解包）
  retriever.py       BM25 + 字符 n-gram TF-IDF 混合检索
  generator.py       本地摘录 fallback + OpenAI 兼容模型生成
  loader.py          本地文件加载和切分，含 PDF 解析
  tracing.py         append-only JSONL trace 持久化
  cost.py            token 估算和多模型定价表
  evaluate.py        eval cases 驱动的自动评测
  schema.py          核心数据结构（DocumentChunk / ToolResult / UsageStats）
main.py              CLI 入口（支持 --mcp-url 切换后端）
server.py            FastAPI 服务入口（lifespan 单例 + 前端托管）
frontend/            Web 控制台（原生 HTML/CSS/JS）
examples/            示例知识库和 eval cases
tests/               单元测试
scripts/             检查脚本（语法 + 单测 + 评测 + 前端 JS）
docs/                架构文档
```

## 环境安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

依赖清单（`requirements.txt`）：

```text
fastapi
uvicorn
openai
pymupdf
mcp>=2.0
```

本地模式只需 `fastapi`/`uvicorn`/`openai`/`pymupdf`；MCP 模式额外需要 `mcp` SDK。无向量数据库、无 embedding 模型、无 LangChain 依赖。

## 知识库配置

把知识文件放到 `data/knowledge/` 目录，支持以下文件类型：

```text
.txt .md .py .json .csv .log .pdf
```

推荐目录结构：

```text
data/
  knowledge/
    your-doc.md
    notes.txt
    api.json
    paper.pdf
```

在 `.env` 中配置：

```text
AGENT_DATA_DIR=./data/knowledge
```

`data/` 已加入 `.gitignore`，不会提交到仓库。不指定目录时默认读取 `examples/knowledge`。

## 本地模式运行

### CLI

```powershell
python main.py --data-dir .\data\knowledge "TraceFlow 是什么项目"
```

查看完整 trace：

```powershell
python main.py --show-trace --data-dir .\data\knowledge "统计当前知识库"
```

交互模式（不提供 query）：

```powershell
python main.py --data-dir .\data\knowledge
```

### Web 服务

```powershell
$env:AGENT_DATA_DIR=".\data\knowledge"
python -m uvicorn server:app --host 127.0.0.1 --port 8010
```

浏览器打开 `http://127.0.0.1:8010/`，接口文档 `http://127.0.0.1:8010/docs`。

## MCP 模式运行（对接 TraceRAG）

MCP 模式下，检索委托给 TraceRAG 后端，获得向量检索、HyDE 查询改写和 CrossEncoder 精排能力。

### 启动 TraceRAG 后端

```powershell
cd C:\path\to\rag_project
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8090
```

TraceRAG 启动后在 `/mcp` 暴露以下 MCP 工具：

| 工具 | 说明 |
|---|---|
| `rag_search` | 混合检索 + HyDE + 精排，返回 sources（含 rerank score）和检索 trace |
| `rag_ask` | 端到端问答（检索 + 精排 + 生成） |
| `rag_corpus_stats` | 语料统计（PDF 数、chunk 数、embedding/generation 模型信息） |
| `rag_collections` | 列出可用 collection 及其 PDF 文件 |

### 启动 TraceFlow（MCP 模式）

CLI：

```powershell
python main.py --mcp-url http://127.0.0.1:8090/mcp "TCP 三次握手过程"
```

Web 服务：

```powershell
$env:AGENT_MCP_URL="http://127.0.0.1:8090/mcp"
python -m uvicorn server:app --host 127.0.0.1 --port 8010
```

不配 `--mcp-url` / `AGENT_MCP_URL` 时自动回退本地 BM25 检索，完全向后兼容。

## 大模型配置

`.env` 使用 OpenAI 兼容风格变量：

```text
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

`OPENAI_BASE_URL` 设为 `https://api.deepseek.com` 时识别为 DeepSeek provider。也支持 Qwen、GLM 等 OpenAI 兼容接口，修改 `base_url` 和 `model` 即可。

模型调用失败时，系统不会崩溃：

1. 回退到基于检索证据的摘录式回答。
2. 在 trace 里记录 `answer_generator` 错误步骤。
3. 前端仍然能看到 sources、trace 和 usage。

## Trace 链路

每次运行产生两层 trace：

**Agent 层 trace**（`result.trace`，前端 Trace 面板展示）：

```text
step 1, tool: search_knowledge_base
  arguments: {query, top_k}
  result.output.retrieval_mode: "hybrid_bm25_ngram_tfidf" | "mcp_tracerag_hybrid"
  result.output.sources: [{chunk_id, source, preview, content, score, ...}]
  result.output.retrieval_trace: {...}   ← MCP 模式下嵌套的后端诊断
  result.attempts: [{attempt, result}]   ← 重试记录
```

**TraceRAG 检索诊断**（MCP 模式下嵌套在 `retrieval_trace` 中）：

```text
hyde: {used, error, doc_preview}                   ← HyDE 假想文档状态
code_query: false                                    ← 是否代码查询
candidate_count / reranked_count / final_context_count
fusion_scores: [{chunk_id, rrf_score}]               ← RRF 融合分数
rerank_scores: [{chunk_id, score}]                   ← CrossEncoder 精排分数
timing_ms: {hyde, retrieval, rerank, context_expansion, total}
```

前端 Trace 面板以 JSON 展示完整两层 trace。Replay 时比较两次运行的工具路径、来源重合度和 token/cost 变化。

## API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/` | GET | Web 控制台 |
| `/health` | GET | 服务健康状态 |
| `/stats` | GET | 语料统计、工具列表、模型信息、后端模式（local / mcp_tracerag） |
| `/config` | GET | Agent 配置（top_k、重试、trace 持久化） |
| `/traces` | GET | 最近运行记录（默认 20 条） |
| `/agent` | POST | 执行 Agent 工作流（query + top_k） |
| `/replay/{run_id}` | POST | 回放历史请求并对比 |

调用示例：

```powershell
curl -X POST http://127.0.0.1:8010/agent `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"Dijkstra算法适合解决什么问题\",\"top_k\":4}"
```

## 评测

在 `examples/eval_questions.jsonl` 中配置评测问题：

```jsonl
{"question":"AgentFlow stage one capabilities","expected_tool":"search_knowledge_base","expected_keywords":["hybrid","BM25","retrieval"],"expected_sources":["agentflow.md"]}
```

运行评测：

```powershell
python -m src.evaluate --eval-file .\examples\eval_questions.jsonl
```

生成评测报告：

```powershell
python -m src.evaluate --report-file .\runs\eval_report.json
```

本地确定性评测（禁用外部模型调用，用于 CI）：

```powershell
python -m src.evaluate --local-only --no-persist-traces
```

## 测试

```powershell
python -m unittest discover -s tests
```

全量检查（语法 + 单测 + 评测 + 前端 JS）：

```powershell
python scripts\checks.py
```

测试覆盖：

| 测试 | 覆盖内容 |
|---|---|
| 检索工作流 | trace 结构、sources、score_details、retrieval_mode |
| 统计路由 | 中英文关键词触发 `get_corpus_stats` |
| Trace 持久化 | run_id 写入、按 run_id 读取、query 一致性 |
| 工具重试 | 首次失败 → 重试成功，attempts 记录完整 |
| 模型降级 | 模型调用失败 → 本地摘录回退，trace 记录 error |
| PDF 加载 | PyMuPDF 按页解析，page/chunk_id 元数据完整 |

## 配置项

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AGENT_DATA_DIR` | `./examples/knowledge` | 本地知识库目录 |
| `AGENT_MCP_URL` | （空） | TraceRAG MCP 端点，设置后切换到 MCP 模式 |
| `AGENT_CHUNK_SIZE` | `700` | 本地模式 chunk 大小 |
| `AGENT_CHUNK_OVERLAP` | `100` | 本地模式 chunk 重叠 |
| `AGENT_TOP_K` | `4` | 检索返回的 chunk 数量 |
| `AGENT_MAX_TOOL_RETRIES` | `1` | 工具失败重试次数 |
| `AGENT_TRACE_DIR` | `./runs/traces` | trace 文件目录 |
| `AGENT_PERSIST_TRACES` | `true` | 是否持久化 trace |
| `OPENAI_API_KEY` | （空） | OpenAI 兼容 API 密钥 |
| `OPENAI_BASE_URL` | （空） | API 地址 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 模型名称 |

### CLI 参数

```text
python main.py --help

参数：
  query               提问内容（省略则进入交互模式）
  --data-dir          本地知识库目录（默认 ./examples/knowledge）
  --chunk-size        chunk 大小（默认 700）
  --chunk-overlap     chunk 重叠（默认 100）
  --top-k             检索返回数量（默认 4）
  --max-tool-retries  工具重试次数（默认 1）
  --trace-dir         trace 目录（默认 ./runs/traces）
  --no-persist-traces  禁用 trace 持久化
  --show-trace        打印完整 trace JSON
  --mcp-url           TraceRAG MCP 端点 URL
```

## 注意事项

- MCP 模式需要先启动 TraceRAG 后端（首次加载 bge-m3 和 bge-reranker 约 1-3 分钟）。
- TraceRAG 后端的 bge-m3/bge-reranker 模型约 4.4GB，首次下载需要较长时间。
- 不配 `AGENT_MCP_URL` 时自动使用本地 BM25 检索，无需任何模型下载。
- `.env` 文件包含 API 密钥，已被 `.gitignore` 忽略，不会提交到仓库。
- `runs/` 目录存储 trace 和评测报告，已被 `.gitignore` 忽略。
- MCP 协议层使用官方 Python SDK（`mcp` 包），非自实现协议解析。
