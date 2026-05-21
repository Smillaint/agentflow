const form = document.querySelector("#agentForm");
const queryInput = document.querySelector("#queryInput");
const topKInput = document.querySelector("#topKInput");
const runButton = document.querySelector("#runButton");
const answerState = document.querySelector("#answerState");
const answerOutput = document.querySelector("#answerOutput");
const sourcesOutput = document.querySelector("#sourcesOutput");
const traceOutput = document.querySelector("#traceOutput");
const traceList = document.querySelector("#traceList");
const languageSelect = document.querySelector("#languageSelect");

const healthStatus = document.querySelector("#healthStatus");
const modelName = document.querySelector("#modelName");
const providerName = document.querySelector("#providerName");
const llmStatus = document.querySelector("#llmStatus");
const chunkCount = document.querySelector("#chunkCount");
const toolList = document.querySelector("#toolList");
const totalTokens = document.querySelector("#totalTokens");
const estimatedCost = document.querySelector("#estimatedCost");
const runId = document.querySelector("#runId");
const sourceCount = document.querySelector("#sourceCount");
const traceCount = document.querySelector("#traceCount");

const messages = {
  en: {
    subtitle: "RAG Agent Console",
    runtime: "Runtime",
    status: "Status",
    model: "Model",
    provider: "Provider",
    llm: "LLM",
    enabled: "Enabled",
    fallback: "Fallback",
    chunks: "Chunks",
    tools: "Tools",
    recentRuns: "Recent Runs",
    runAgent: "Run Agent",
    runHint: "Ask against the local knowledge base and inspect the execution trace.",
    apiDocs: "API Docs",
    topK: "Top K",
    runButton: "Run Agent",
    sampleStageOne: "Stage one",
    sampleStageTwo: "Stage two",
    sampleStats: "Stats",
    totalTokens: "Total Tokens",
    estimatedCost: "Estimated Cost",
    runId: "Run ID",
    answer: "Answer",
    emptyAnswer: "Run the agent to see a grounded answer.",
    sources: "Sources",
    trace: "Trace",
    ready: "Ready",
    loading: "Loading",
    idle: "Idle",
    running: "Running",
    done: "Done",
    loaded: "Loaded",
    error: "Error",
    noSources: "No sources returned.",
    noTrace: "No trace steps.",
    noRuns: "No runs yet.",
    runningText: "Running agent workflow...",
    steps: "steps",
    step: "step",
    attempts: "attempts",
    score: "score",
  },
  zh: {
    subtitle: "RAG Agent 控制台",
    runtime: "运行状态",
    status: "状态",
    model: "模型",
    provider: "提供方",
    llm: "大模型",
    enabled: "已启用",
    fallback: "本地回退",
    chunks: "分片数",
    tools: "工具",
    recentRuns: "最近运行",
    runAgent: "运行 Agent",
    runHint: "基于本地知识库提问，并检查工具调用 trace。",
    apiDocs: "接口文档",
    topK: "Top K",
    runButton: "运行 Agent",
    sampleStageOne: "第一阶段",
    sampleStageTwo: "第二阶段",
    sampleStats: "统计",
    totalTokens: "总 Token",
    estimatedCost: "估算成本",
    runId: "运行 ID",
    answer: "回答",
    emptyAnswer: "运行 Agent 后查看 grounded answer。",
    sources: "来源",
    trace: "Trace",
    ready: "就绪",
    loading: "加载中",
    idle: "空闲",
    running: "运行中",
    done: "完成",
    loaded: "已加载",
    error: "错误",
    noSources: "没有返回来源。",
    noTrace: "没有 trace 步骤。",
    noRuns: "暂无运行记录。",
    runningText: "正在运行 Agent 工作流...",
    steps: "步",
    step: "步骤",
    attempts: "次尝试",
    score: "分数",
  },
};

let currentLanguage = localStorage.getItem("agentflow-language") || "en";

function t(key) {
  return messages[currentLanguage][key] || messages.en[key] || key;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function applyLanguage(language) {
  currentLanguage = language;
  localStorage.setItem("agentflow-language", language);
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.dataset.i18n;
    node.textContent = t(key);
  });
  document.querySelectorAll(".sample-button").forEach((button) => {
    button.textContent = t(button.dataset.key);
  });
  if (answerState.textContent) {
    const stateKey = answerState.dataset.stateKey || "idle";
    setState(stateKey, answerState.dataset.stateClass || "");
  }
}

function setState(key, className) {
  answerState.dataset.stateKey = key;
  answerState.dataset.stateClass = className || "";
  answerState.textContent = t(key);
  answerState.className = `state-pill ${className || ""}`.trim();
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function renderStats(stats, health) {
  const llm = stats?.llm || {};
  healthStatus.textContent = health?.ready ? t("ready") : t("loading");
  modelName.textContent = llm.model || stats?.model || "-";
  providerName.textContent = llm.provider || "-";
  llmStatus.textContent = llm.llm_enabled ? t("enabled") : t("fallback");
  chunkCount.textContent = stats?.chunk_count ?? "-";
  toolList.textContent = Array.isArray(stats?.tools) ? stats.tools.join(", ") : "-";
}

function renderUsage(usage, id) {
  totalTokens.textContent = usage?.total_tokens ?? "-";
  estimatedCost.textContent =
    typeof usage?.estimated_cost_usd === "number"
      ? `$${usage.estimated_cost_usd.toFixed(8)}`
      : "-";
  runId.textContent = id || "-";
}

function renderSources(sources) {
  sourceCount.textContent = `${sources.length}`;
  if (!sources.length) {
    sourcesOutput.innerHTML = `<div class="muted">${t("noSources")}</div>`;
    return;
  }

  sourcesOutput.innerHTML = sources
    .map((source) => {
      const score = source.score === undefined ? "" : `<span class="tag">${t("score")} ${source.score}</span>`;
      return `
        <div class="source-item">
          <div class="source-meta">
            <span class="tag">${escapeHtml(source.source || "unknown")}</span>
            <span class="tag">${escapeHtml(source.chunk_id || "chunk")}</span>
            ${score}
          </div>
          <div>${escapeHtml(source.preview || source.content || "")}</div>
        </div>
      `;
    })
    .join("");
}

function renderTrace(trace) {
  traceCount.textContent = `${trace.length} ${t("steps")}`;
  if (!trace.length) {
    traceOutput.innerHTML = `<div class="muted">${t("noTrace")}</div>`;
    return;
  }

  traceOutput.innerHTML = trace
    .map((step) => {
      const attempts = step.result?.attempts?.length ?? 0;
      return `
        <div class="trace-step">
          <div class="trace-meta">
            <span class="tag">${t("step")} ${escapeHtml(step.step)}</span>
            <span class="tag">${escapeHtml(step.tool)}</span>
            <span class="tag">${attempts} ${t("attempts")}</span>
          </div>
          <pre>${escapeHtml(JSON.stringify(step, null, 2))}</pre>
        </div>
      `;
    })
    .join("");
}

function renderResult(result) {
  answerOutput.textContent = result.answer || "";
  renderUsage(result.usage, result.run_id);
  renderSources(result.sources || []);
  renderTrace(result.trace || []);
}

function renderTraceList(records) {
  if (!records.length) {
    traceList.innerHTML = `<div class="muted">${t("noRuns")}</div>`;
    return;
  }

  traceList.innerHTML = records
    .map((record) => `
      <div class="run-item">
        <button type="button" data-run='${escapeHtml(JSON.stringify(record))}'>
          ${escapeHtml(record.query || "Untitled run")}
        </button>
        <small>${escapeHtml(record.run_id || "")}</small>
      </div>
    `)
    .join("");

  traceList.querySelectorAll("button[data-run]").forEach((button) => {
    button.addEventListener("click", () => {
      const record = JSON.parse(button.dataset.run);
      renderResult(record);
      setState("loaded", "done");
    });
  });
}

async function loadStats() {
  const [health, stats] = await Promise.all([
    requestJson("/health"),
    requestJson("/stats"),
  ]);
  renderStats(stats, health);
}

async function loadTraces() {
  const data = await requestJson("/traces?limit=10");
  renderTraceList(data.traces || []);
}

async function runAgent(event) {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) {
    queryInput.focus();
    return;
  }

  setState("running", "running");
  runButton.disabled = true;
  answerOutput.textContent = t("runningText");

  try {
    const result = await requestJson("/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        top_k: Number(topKInput.value || 4),
      }),
    });
    renderResult(result);
    setState("done", "done");
    await Promise.all([loadStats(), loadTraces()]);
  } catch (error) {
    setState("error", "error");
    answerOutput.textContent = error.message;
  } finally {
    runButton.disabled = false;
  }
}

document.querySelector("#refreshStats").addEventListener("click", () => {
  loadStats().catch((error) => {
    healthStatus.textContent = error.message;
  });
});

document.querySelector("#refreshTraces").addEventListener("click", () => {
  loadTraces().catch((error) => {
    traceList.innerHTML = `<div class="muted">${escapeHtml(error.message)}</div>`;
  });
});

document.querySelectorAll(".sample-button").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset[currentLanguage === "zh" ? "queryZh" : "queryEn"];
    queryInput.focus();
  });
});

languageSelect.addEventListener("change", () => {
  applyLanguage(languageSelect.value);
  loadStats().catch(() => {});
  loadTraces().catch(() => {});
});

form.addEventListener("submit", runAgent);

languageSelect.value = currentLanguage;
applyLanguage(currentLanguage);
setState("idle", "");

Promise.all([loadStats(), loadTraces()]).catch((error) => {
  setState("error", "error");
  answerOutput.textContent = error.message;
});
