# AgentFlow 面试防守手册

这份文档用于解释 AgentFlow 的边界、设计取舍和容易被追问的实现细节。原则是：不夸大能力，把已经实现的工程部分讲清楚。

## 1. 这到底算不算 Agent

当前实现是一个单 Agent 工作流原型，不是完全由 LLM 自主规划的复杂 Agent。

源码位置：

- `src/agent.py::_plan`
- `src/agent.py::run`
- `src/tools.py::ToolRegistry`

`_plan()` 采用确定性规则路由：

- 查询包含 `统计`、`多少`、`来源`、`stats` 等关键词时调用 `get_corpus_stats`。
- 其他查询调用 `search_knowledge_base`。
- 一次运行通常只调用一个业务工具。

不能这样说：

> 模型自主规划并动态选择多种工具，完成复杂多步推理。

更准确的说法：

> 这是一个可观测的单 Agent 工作流原型。当前采用确定性规则路由，而不是完全由 LLM 自主规划。这样做是为了减少额外模型调用、控制成本并提高可测试性。ToolRegistry、统一 ToolResult、重试、trace、usage 和 replay 已经把执行框架搭好，后续可以替换为 LLM function calling 或多步 planner。

如果面试官问“那这不就是 if-else 吗”，可以回答：

> 当前路由策略确实是规则驱动，但 Agent 的工程部分不只在路由。它还包括统一工具描述和注册、参数边界处理、工具执行、失败重试、来源聚合、生成回退、usage 统计、trace 持久化和 replay。我对它的定位是可观测 Agent 工作流原型，而不是强调复杂自主推理。

## 2. ToolRegistry 的价值

源码位置：

- `src/tools.py::ToolSpec`
- `src/tools.py::ToolRegistry`
- `src/schema.py::ToolResult`

`ToolRegistry` 保存工具定义：

- `name`
- `description`
- `parameters`
- `handler`

`execute()` 通过工具名找到 handler，统一执行，并把未知工具或异常转换成结构化 `ToolResult`。

回答：

> Registry 将工具定义和 Agent 执行逻辑解耦。Agent 不需要知道每个工具的具体实现，只通过名称和参数调用。新增工具只需要注册 ToolSpec，不需要修改执行框架。同时可以统一处理未知工具、异常和返回结构。

追问：`parameters` 是否真的做 JSON Schema 校验？

> 目前没有。当前 `parameters` 主要是描述信息，具体参数校验仍在 handler 内完成，例如 `top_k` 会转换成整数并限制在 1 到 20。后续可以引入 Pydantic 或 JSON Schema，在 Registry 层统一做类型和必填项校验。

## 3. 重试机制的缺点

源码位置：

- `src/agent.py::_execute_with_retries`

当前机制：

- 工具执行失败后直接重试相同调用。
- 默认重试 1 次。
- 没有指数退避、错误分类或参数修正。

回答：

> 当前 MVP 是统一重试，适合覆盖临时异常，但不是所有错误都应该重试。网络超时、临时服务不可用可以重试；参数错误、未知工具、权限错误一般不应重试。后续应根据错误类型分类，并加入指数退避和 jitter。对于非幂等工具，还要避免重复执行造成副作用。

追问：当前工具是否幂等？

> 当前两个工具都是只读操作，搜索知识库和统计语料不会修改状态，因此重复执行基本安全。如果加入写数据库、发消息等工具，就必须引入幂等键和执行状态记录。

## 4. Trace 记录了什么，为什么用 JSONL

源码位置：

- `src/tracing.py::TraceStore`
- `src/agent.py::run`

每次运行会记录：

- `run_id`
- `created_at`
- `query`
- `tool`
- `arguments`
- 每次 `attempt`
- `result` 或 `error`
- `sources`
- `answer`
- `usage`

回答：

> JSONL 每行是一条独立记录，适合追加写、流式读取、人工检查和脚本处理。对于本地原型，它比数据库更轻量，也更容易直接查看 trace。

追问：JSONL 有什么问题？

> 查询和聚合效率低，`get(run_id)` 需要顺序扫描，`list_recent` 也会读取文件内容；并发写入时缺少锁，进程崩溃可能造成半行记录。数据量增大后应该切换 SQLite、PostgreSQL 或日志系统，并增加索引、并发控制和文件轮转。

## 5. Replay 是真正重新执行吗

源码位置：

- `server.py::replay_run`
- `server.py::_compare_runs`

当前 replay 做三件事：

1. 根据 `run_id` 读取历史记录。
2. 使用历史记录里的原始 `query` 重新执行当前 Agent。
3. 比较工具路径、来源 chunk 重合度、token delta 和 cost delta。

回答：

> 当前 replay 是回归对比，不是 bit-level 复现。它会重新执行同一个 query，然后比较新旧结果的工具路径、来源重合度和用量变化。

追问：如何保证可复现？

> 严格可复现很难，因为模型输出、知识库内容和服务版本都可能变化。当前 replay 的目标是观察变化，不是保证完全一致。后续应该额外记录模型名、温度、知识库版本、chunk 参数、检索器版本和 prompt 版本，才能解释结果差异。

## 6. 检索能力应该怎么表述

源码位置：

- `src/retriever.py::BM25Retriever`
- `src/retriever.py::NgramTfidfRetriever`
- `src/retriever.py::HybridRetriever`

不能说：

> BM25 + embedding 向量检索。

准确说法：

> BM25 + 字符 n-gram TF-IDF 的词法混合检索。

实现要点：

- BM25 用于关键词、缩写、代码类精确匹配。
- 字符 2-gram、3-gram 加 token 的 TF-IDF 用于补充局部字符串匹配。
- 两路分数归一化后按权重融合。
- 返回 `score_details`，包含原始分数、归一化分数和融合权重。

追问：为什么不用 embedding？

> AgentFlow 的目标之一是离线、低依赖和可解释，因此先使用无模型的 n-gram TF-IDF 补充 BM25。它能够缓解中文切词、拼写变化和局部字符串匹配问题，每个结果也能展示两路原始分数和融合权重。缺点是语义泛化能力不如 embedding，后续可以保留 retriever 抽象，同时替换或叠加向量检索实现。

## 7. 本地回退是不是 extractive answer

源码位置：

- `src/generator.py::generate`
- `src/generator.py::_generate_local`

当前 fallback 会把前几个 source 的 `preview` 原样列出，并附 `chunk_id`。它更接近“证据摘录”，没有做复杂的句子抽取排序或答案压缩。

回答：

> 模型不可用时，系统回退为基于检索证据的摘录式回答，而不是调用另一个生成模型。它不能提供高质量归纳，但可以保证用户至少看到相关证据和 chunk 引用，避免整个请求失败。

## 8. Git 被追问时怎么答

当前工程分支：

- `main`：稳定分支。
- `codex/engineering-workflow`：工程化分支，包含 CI、检查脚本、Git 工作流文档和回归测试。

常用命令：

```powershell
git fetch origin
git switch -c codex/engineering-workflow --track origin/codex/engineering-workflow
```

如果本地已有分支：

```powershell
git switch codex/engineering-workflow
```

查看提交图：

```powershell
git log --oneline --decorate --graph --all
```

回答：

> 我现在用 `main` 作为稳定分支，功能或工程化改动放到短生命周期分支。每个提交尽量只表达一个意图，例如补回归测试、加 CI、加工具脚本。push 前运行 `python scripts/checks.py`，GitHub Actions 也跑同一套检查。
