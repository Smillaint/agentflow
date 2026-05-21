# AgentFlow MVP

AgentFlow is a resume-oriented local RAG + tool-calling Agent project. The goal is not a simple chatbot demo, but a testable Agent backend with traceability, evaluation, usage accounting, and a small operations console.

Chinese documentation: [README.zh-CN.md](README.zh-CN.md)

## Capabilities

Stage 1:

- Local knowledge loading for `.txt`, `.md`, `.py`, `.json`, `.csv`, `.log`, and `.pdf`.
- BM25 retrieval with source metadata.
- Tool calling through a central `ToolRegistry`.
- Single-Agent workflow with planning, tool execution, answer generation, trace output, and sources.
- FastAPI endpoints for `/health`, `/stats`, `/agent`.
- Core tests that do not require an external LLM.

Stage 2:

- JSONL trace persistence with `run_id`, query, answer, trace, sources, and usage.
- Eval runner with JSONL cases, expected tool checks, keyword checks, and pass rate.
- Tool failure retry with every attempt recorded in trace.
- Token and estimated cost accounting.
- `/traces` endpoint for recent run inspection.

Stage 3:

- Static web console served by FastAPI at `/`.
- Query form, runtime stats, answer panel, sources panel, trace viewer, usage metrics, and recent runs.
- `/docs` remains available as the FastAPI API debugger.
- Runtime model panel showing provider, model, LLM status, and token/cost usage.
- English / Chinese UI switch in the web console.

## Project Structure

```text
frontend/
  index.html     Agent console shell
  styles.css     Responsive operations UI
  app.js         API client and render logic
src/
  agent.py       Single-Agent workflow
  cost.py        Token and cost estimation
  evaluate.py    Eval runner
  generator.py   Local fallback and OpenAI-compatible generation
  loader.py      Local file loading and chunking
  retriever.py   BM25 retrieval
  schema.py      Core data structures
  tools.py       Tool registry and built-in tools
  tracing.py     JSONL trace persistence
main.py          CLI entry
server.py        FastAPI service and frontend hosting
examples/        Demo knowledge base and eval cases
tests/           Unit tests
docs/            Architecture notes
```

## Run From CLI

```powershell
python main.py --data-dir .\examples\knowledge "What capabilities are included in AgentFlow stage one?"
```

For real local knowledge files, put them under:

```text
data/knowledge
```

Then run:

```powershell
python main.py --data-dir .\data\knowledge "your question"
```

Supported local knowledge file types:

```text
.txt .md .py .json .csv .log .pdf
```

PDF parsing uses PyMuPDF, included in `requirements.txt` as `pymupdf`.

Show trace:

```powershell
python main.py --show-trace --data-dir .\examples\knowledge "Show knowledge base stats"
```

## Run The Web Console

Install API dependencies:

```powershell
pip install -r requirements.txt
```

Start the service on your available port:

```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8010
```

Open:

```text
http://127.0.0.1:8010/
```

The console can switch between English and Chinese from the language selector in the top-right toolbar.

API docs:

```text
http://127.0.0.1:8010/docs
```

## Optional LLM Configuration

Without an API key, AgentFlow uses a local extractive fallback. To enable DeepSeek, OpenAI, or another OpenAI-compatible API:

```text
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

AgentFlow detects the provider from `OPENAI_BASE_URL` and `OPENAI_MODEL`. With `https://api.deepseek.com` and `deepseek-chat`, the UI will show provider `deepseek`.

If the model request fails, AgentFlow falls back to the local extractive answer and records the model error in trace as an `answer_generator` step.

## Evaluation

Run tests:

```powershell
python -m unittest discover -s tests
```

Run eval cases:

```powershell
python -m src.evaluate --eval-file .\examples\eval_questions.jsonl
```

Write an eval report:

```powershell
python -m src.evaluate --report-file .\runs\eval_report.json
```

