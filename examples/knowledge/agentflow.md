# TraceFlow 项目概览

TraceFlow 是一个可观测的单 Agent RAG 工作流框架，覆盖工具路由、答案生成、执行追踪、回放和自动评测。

## 核心能力

- 通过 `ToolRegistry` 统一管理工具，内置 `search_knowledge_base` 和 `get_corpus_stats`。
- 单 Agent 确定性路由：根据查询关键词判断调用检索还是统计工具。
- 本地模式：BM25 + 字符 n-gram TF-IDF 混合检索，返回分数解释。
- MCP 模式：通过 MCP 协议对接 TraceRAG 后端，获得向量检索、HyDE 查询改写和 CrossEncoder 精排。
- 每次运行保存 JSONL trace，支持按 `run_id` replay 并比较工具路径、来源重合度和 token/cost 变化。
- 工具失败自动重试，每次 attempt 记录在 trace 中。
- 答案生成支持 DeepSeek / OpenAI 兼容 API，失败回退本地摘录式回答。
- FastAPI 托管前端控制台，支持中英文界面切换。

## 两种运行模式

本地模式使用内置混合词法检索，无需外部依赖。MCP 模式通过 `--mcp-url` 指定 TraceRAG 端点，检索委托给后端，Agent 层的路由、生成、trace、replay 逻辑不变。
