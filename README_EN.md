# TraceFlow — Observable Agent Workflow Framework

An observable single-agent workflow framework for knowledge base QA. Built around tool routing, execution tracing, replay comparison, and automated evaluation. Connects to retrieval backends via the MCP protocol to provide explainable, reproducible, and evaluable Agent infrastructure for LLM applications.

Chinese documentation: [README.md](README.md)

## Features

- `ToolRegistry` centrally manages tools with built-in `search_knowledge_base` and `get_corpus_stats`, supporting hot-swapping.
- Single-agent deterministic routing: keyword detection (EN/ZH) decides tool selection without LLM involvement, ensuring reproducible results.
- Tool failure auto-retry with every attempt recorded in trace for fault diagnosis.
- **Two-layer trace**: Agent-layer trace records tool call steps, arguments, results, and retries; MCP mode nests backend retrieval diagnostics (HyDE status, RRF fusion scores, rerank scores, per-stage timing).
- Each run generates a unique `run_id`, persisted as JSONL, supporting replay by `run_id` with tool-path consistency, source overlap (Jaccard), and token/cost delta comparison.
- **MCP protocol integration**: StreamableHTTP transport connects to retrieval backends; tool discovery and invocation follow the standard MCP protocol with zero hardcoding on the client side.
- Answer generation supports DeepSeek / OpenAI / any OpenAI-compatible API with automatic provider detection; falls back to local extractive answers on model failure with error recorded in trace.
- Local mode uses pure-Python BM25 + char n-gram TF-IDF hybrid retrieval with zero vector database dependency, returning raw/norm/fused scores per chunk.
- Token usage accounting and cost estimation with multi-model pricing table.
- Automated evaluation framework: eval-case-driven tool selection, keyword hit, and source hit checks, outputting pass rate and latency report.
- FastAPI-hosted web console with query, answer, sources, trace, usage, recent runs, and EN/ZH UI switch.

## Tech Stack

### Agent Workflow

| Component | Choice | Design Rationale |
|---|---|---|
| Tool Management | `ToolRegistry` pattern | Unified registration, naming, execution entry; tool failures caught as `ToolResult.error` without breaking the agent; supports local and MCP registry implementations |
| Routing | Deterministic keyword routing | EN/ZH keyword matching (stats/统计/how many/多少), no LLM in routing decision, reproducible and low latency; extensible to LLM function calling |
| Retry | Attempt-level recording | Each tool call (including failures) recorded as an independent attempt in trace; `max_tool_retries` configurable; last successful result used as output |
| Generation | OpenAI-compatible API | Supports DeepSeek/OpenAI/any compatible API; auto-infers provider from `base_url` and `model`; system prompt constrains answers to retrieved chunks with chunk_id citations |
| Fallback | Local extractive answer | No crash on model failure: falls back to evidence-excerpt answer, records `answer_generator` error in trace, frontend still shows sources/trace/usage |

### Retrieval

| Component | Choice | Design Rationale |
|---|---|---|
| Local Retrieval | BM25 + char n-gram TF-IDF | Pure Python stdlib, zero external deps; BM25 for exact terms/acronyms/code, n-gram TF-IDF for Chinese partial string matching; returns raw/norm/fused scores |
| Hybrid Fusion | Weighted linear fusion | BM25 weight 0.65 + vector weight 0.35; max normalization eliminates scale differences; per-chunk `score_details` records both raw scores and fusion weights |
| MCP Remote Retrieval | StreamableHTTP transport | Connects to TraceRAG backend: bge-m3 vector + BM25 weighted RRF + HyDE + bge-reranker CrossEncoder; retrieval trace nested in Agent trace |
| File Loading | PyMuPDF + recursive windowing | Supports `.txt .md .py .json .csv .log .pdf`; paragraph/newline/punctuation-aware splitting with `chunk_id`/`char_start`/`char_end` metadata |

### Observability

| Component | Choice | Design Rationale |
|---|---|---|
| Trace Persistence | Append-only JSONL | Each run appends one record with `run_id`/`query`/`answer`/`trace`/`sources`/`usage`/`created_at`; append-only ensures non-blocking writes, easy offline analysis |
| Replay | run_id-level replay | Fetches historical request by `run_id` and reruns, auto-compares tool-path consistency, source Jaccard overlap, token/cost delta; validates config changes or model upgrades |
| Cost Accounting | Multi-model pricing table | Local mode estimates tokens by character (ASCII ÷ 4 + non-ASCII ÷ 2), model mode reads real API usage; looks up pricing by model name for USD cost |
| Call Chain | Structured trace dict | Each step records step number, tool name, arguments, result (with attempts); MCP mode nests `retrieval_trace` (HyDE/RRF/rerank/timing) in result.output |

### Evaluation

| Component | Choice | Design Rationale |
|---|---|---|
| Eval-Driven | JSONL cases | Each case has question, expected_tool, expected_keywords, expected_sources; after real agent run, checks tool selection, keyword hit, source hit |
| Report | Pass rate + latency | Per-case passed/tool_hit/keyword_hit/source_hit/latency_ms/usage; aggregated pass_rate/avg_latency/total_usage; supports JSON report output |
| Deterministic | `--local-only` | Disables external model calls, ensures reproducible eval in CI |

### Service & Frontend

| Component | Choice | Design Rationale |
|---|---|---|
| API | FastAPI + Uvicorn | lifespan manages singleton Agent; requests reuse in-memory registry/generator/trace_store; Pydantic request validation |
| Web Console | Native HTML/CSS/JS | No framework, no build step; FastAPI `StaticFiles` serves `/assets`, `/` returns `index.html` |
| Communication | fetch + JSON | `/agent` POST sends query, returns answer/trace/sources/usage/run_id; `/traces` GET fetches recent runs; `/stats` GET fetches runtime status |
| i18n | Runtime switch | localStorage persists language; `data-i18n` attribute + `messages` dict for EN/ZH, no i18n library |

### MCP Protocol Layer

| Component | Choice | Design Rationale |
|---|---|---|
| Transport | StreamableHTTP | Official MCP Python SDK (`mcp>=2.0`); backend `MCPServer.streamable_http_app()` mounted as ASGI sub-app sharing FastAPI process; client `streamable_http_client` establishes sessions |
| Server | `MCPServer` + `@tool()` | Decorator registers tools, auto-generates JSON Schema; tool functions synchronous (reranker is CPU-bound), MCP runtime dispatches in worker thread |
| Client | Stateless sessions | Each `call_tool` independently: session → initialize → call_tool → close; `asyncio.run` bridges synchronous `ToolRegistry`; ExceptionGroup auto-unwrapped to readable errors |
| Tool Mapping | Name alignment | MCP tool names (`rag_search` → `search_knowledge_base`) match local registry, `SingleAgent` routing unchanged; `build_mcp_registry` wraps remote tools as `ToolSpec` |

## Architecture

```text
User query
  -> SingleAgent deterministic routing (keyword detection)
  -> ToolRegistry executes tool (auto-retry on failure)
  │
  ├── Local mode: BM25 + n-gram TF-IDF hybrid retrieval
  └── MCP mode: StreamableHTTP -> TraceRAG backend
                 -> bge-m3 vector + BM25 -> RRF fusion
                 -> HyDE hypothetical document query rewriting
                 -> bge-reranker CrossEncoder reranking
                 -> code-query neighbor expansion
  -> AnswerGenerator (model failure falls back to local excerpt)
  -> TraceStore JSONL persistence
  -> answer + trace + sources + usage + run_id
```

## Project Structure

```text
src/
  agent.py           Single-agent workflow (routing, execution, retry, trace assembly)
  tools.py           ToolRegistry + local tools + MCP registry builder
  mcp_client.py      MCP StreamableHTTP client (stateless session + exception unwrap)
  retriever.py       BM25 + char n-gram TF-IDF hybrid retrieval
  generator.py       Local excerpt fallback + OpenAI-compatible generation
  loader.py          Local file loading and chunking, with PDF parsing
  tracing.py         Append-only JSONL trace persistence
  cost.py            Token estimation and multi-model pricing table
  evaluate.py        Eval-case-driven automated evaluation
  schema.py          Core data structures (DocumentChunk / ToolResult / UsageStats)
main.py              CLI entry (supports --mcp-url for backend switching)
server.py            FastAPI service (lifespan singleton + frontend hosting)
frontend/            Web console (native HTML/CSS/JS)
examples/            Demo knowledge base and eval cases
tests/               Unit tests
scripts/             Check scripts (syntax + tests + eval + frontend JS)
docs/                Architecture docs
```

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Dependencies (`requirements.txt`):

```text
fastapi
uvicorn
openai
pymupdf
mcp>=2.0
```

Local mode requires only `fastapi`/`uvicorn`/`openai`/`pymupdf`; MCP mode additionally needs the `mcp` SDK. No vector database, no embedding model, no LangChain dependency.

## Quick Start

### Local Mode (CLI)

```powershell
python main.py --data-dir .\data\knowledge "your question"
```

### Local Mode (Web)

```powershell
$env:AGENT_DATA_DIR=".\data\knowledge"
python -m uvicorn server:app --host 127.0.0.1 --port 8010
```

Open `http://127.0.0.1:8010/`.

### MCP Mode (TraceRAG Backend)

Start TraceRAG backend first:

```powershell
cd C:\path\to\rag_project
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8090
```

Then start TraceFlow with MCP:

```powershell
python main.py --mcp-url http://127.0.0.1:8090/mcp "TCP three-way handshake process"
```

Without `--mcp-url` / `AGENT_MCP_URL`, TraceFlow falls back to local BM25 retrieval — fully backward compatible.

## LLM Configuration

`.env` uses OpenAI-compatible variables:

```text
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

Supports Qwen, GLM, and other OpenAI-compatible APIs by changing `base_url` and `model`.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web console |
| `/health` | GET | Service health |
| `/stats` | GET | Corpus stats, tools, model info, backend mode |
| `/config` | GET | Agent configuration |
| `/traces` | GET | Recent runs |
| `/agent` | POST | Run agent workflow |
| `/replay/{run_id}` | POST | Replay and compare a run |

## Testing

```powershell
python -m unittest discover -s tests
python scripts\checks.py
```
