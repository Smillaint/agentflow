# Architecture

## Stage 1 Pipeline

```text
Local files
  -> load_knowledge_base()
  -> BM25Retriever
  -> ToolRegistry
  -> SingleAgent plan
  -> tool execution with retry
  -> AnswerGenerator
  -> usage estimation
  -> TraceStore JSONL persistence
  -> answer + trace + sources + usage + run_id
```

## Design Choices

- 第一阶段不强依赖向量数据库，先用纯 Python BM25 保证项目可运行、可测试。
- `ToolRegistry` 统一管理工具，后续可以扩展 SQL、HTTP、代码搜索、工单系统等工具。
- `SingleAgent` 返回完整 trace，后续可以直接扩展为 AgentOps、回放和自动评测。
- `AnswerGenerator` 默认使用本地 fallback；配置 `OPENAI_API_KEY` 后切换到 OpenAI-compatible 大模型。
- `TraceStore` 使用 append-only JSONL，便于离线分析、复现和评测。
- `src.evaluate` 把 eval case 和真实 Agent run 打通，先覆盖工具选择和关键词命中。
- `UsageStats` 当前采用轻量 token/cost 估算，接入模型后会优先读取 API usage。
- `AnswerGenerator` uses a grounded prompt that requires chunk_id citations and refuses unsupported facts.
- Model errors are captured as an `answer_generator` trace step, then the system falls back to local extractive output.
- The web console exposes provider, model, LLM status, usage, trace, and bilingual UI switching.

## Stage 2 Runtime Record

Each run returns and persists:

```json
{
  "run_id": "...",
  "query": "...",
  "answer": "...",
  "trace": [],
  "sources": [],
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "estimated_cost_usd": 0.0,
    "model": "local-extractive"
  }
}
```

## Extension Points

- `src/retriever.py`：替换或叠加 embedding、reranker、向量库。
- `src/tools.py`：添加真实业务工具。
- `src/agent.py`：升级为多步骤 planner、预算控制、人工确认。
- `src/generator.py`：增加模型路由、fallback、结构化输出。
- `src/evaluate.py`：增加 Recall@K、MRR、faithfulness、trace-level grading。
