# AgentFlow MVP 中文说明

AgentFlow 是一个面向简历项目的本地 RAG + 工具调用 Agent 项目,是一个带检索、工具调用、trace、评测、成本统计和前端控制台的 Agent 后端原型。

## 当前能力


- 加载本地知识库文件。
- 使用 BM25 做关键词检索。
- 使用 BM25 + 字符 n-gram TF-IDF 做混合检索，并返回每个 chunk 的分数解释。
- 通过 `ToolRegistry` 统一管理工具。
- 单 Agent 工作流：规划、工具调用、答案生成、trace 输出。
- FastAPI 接口：`/health`、`/stats`、`/agent`。

- 每次运行保存 JSONL trace。
- 支持按 `run_id` replay 历史请求，并比较工具路径、来源重合度和 token/cost 变化。
- 支持自动评测 eval cases。
- 工具失败自动重试，并记录每次 attempt。
- 统计 token 和估算成本。
- `/traces` 查看最近运行记录。

- FastAPI 托管前端控制台。
- 前端支持提问、查看答案、sources、trace、usage 和最近运行。
- 支持中文 / 英文界面切换。
- 显示当前模型、模型提供方和 LLM 是否启用。


### 推荐目录

```text
data/
  knowledge/
    your-doc.md
    notes.txt
    api.json
    paper.pdf
```

### 默认示例目录

如果不指定目录，项目默认读取：

```text
examples/knowledge
```


### 支持的文件类型

当前支持这些文件：

```text
.txt
.md
.py
.json
.csv
.log
.pdf
```

## 如何指定知识库目录？

### CLI 运行

```powershell
python main.py --data-dir .\data\knowledge "AgentFlow 是什么项目"
```

查看完整 trace：

```powershell
python main.py --show-trace --data-dir .\data\knowledge "统计当前知识库"
```

### Web 服务运行

启动服务前设置环境变量,8010只是一个示例端口,换成空闲端口即可：

```powershell
$env:AGENT_DATA_DIR=".\data\knowledge"
python -m uvicorn server:app --host 127.0.0.1 --port 8010
```

然后打开：

```text
http://127.0.0.1:8010/
```

### 写入 `.env`

也可以在项目根目录 `.env` 里加：

```text
AGENT_DATA_DIR=./data/knowledge
```

之后直接启动：

```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8010
```

## 大模型配置

`.env` 使用 OpenAI-compatible 风格变量：

```text
OPENAI_API_KEY=key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

如果 `OPENAI_BASE_URL` 是 `https://api.deepseek.com`，项目会识别为 DeepSeek,其余api请填写对应官网

如果模型调用失败，系统不会直接崩溃，而是：

1. 回退到本地 extractive answer。
2. 在 trace 里记录 `answer_generator` 错误步骤。
3. 前端仍然能看到 sources、trace 和 usage。

## 启动前端控制台

安装依赖：

```powershell
pip install -r requirements.txt
```

启动服务：

```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8010
```

打开：

```text
http://127.0.0.1:8010/
```

接口文档：

```text
http://127.0.0.1:8010/docs
```

## 测试和评测

运行单测：

```powershell
python -m unittest discover -s tests
```

运行评测：

```powershell
python -m src.evaluate --eval-file .\examples\eval_questions.jsonl
```

生成评测报告：

```powershell
python -m src.evaluate --report-file .\runs\eval_report.json
```

## 目录结构

```text
frontend/
  index.html      前端页面
  styles.css      页面样式
  app.js          前端接口调用和渲染逻辑
src/
  agent.py        单 Agent 工作流
  cost.py         token 和成本估算
  evaluate.py     自动评测
  generator.py    本地 fallback + 大模型生成
  loader.py       本地文件加载和切分，包含 PDF 解析
  retriever.py    BM25 检索
  schema.py       核心数据结构
  tools.py        工具注册和内置工具
  tracing.py      JSONL trace 持久化
main.py           CLI 入口
server.py         FastAPI 服务和前端托管
examples/         示例知识库和 eval cases
tests/            单元测试
docs/             架构文档
data/             本地知识库，已被 Git 忽略
```
