# -*- coding: utf-8 -*-
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from main import load_local_env
from src.agent import AgentConfig, SingleAgent
from src.generator import build_generator
from src.loader import load_knowledge_base
from src.retriever import BM25Retriever
from src.tools import build_default_registry


class AgentRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(4, ge=1, le=20)


class AgentResponse(BaseModel):
    answer: str
    trace: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    usage: dict[str, Any]
    run_id: str | None = None
    trace_path: str | None = None


agent: SingleAgent | None = None
chunks_count = 0
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"


def build_agent() -> SingleAgent:
    global chunks_count
    load_local_env()
    chunks = load_knowledge_base(
        os.getenv("AGENT_DATA_DIR", "./examples/knowledge"),
        chunk_size=int(os.getenv("AGENT_CHUNK_SIZE", "700")),
        chunk_overlap=int(os.getenv("AGENT_CHUNK_OVERLAP", "100")),
    )
    chunks_count = len(chunks)
    retriever = BM25Retriever(chunks)
    registry = build_default_registry(chunks, retriever)
    return SingleAgent(
        registry,
        build_generator(),
        AgentConfig(
            max_tool_retries=int(os.getenv("AGENT_MAX_TOOL_RETRIES", "1")),
            trace_dir=os.getenv("AGENT_TRACE_DIR", "./runs/traces"),
            persist_traces=os.getenv("AGENT_PERSIST_TRACES", "true").lower() != "false",
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    agent = build_agent()
    yield
    agent = None


app = FastAPI(
    title="AgentFlow MVP API",
    description="RAG, tool calling, and single-agent workflow service.",
    version="0.1.0",
    lifespan=lifespan,
)

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")


def get_agent() -> SingleAgent:
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent is not ready.")
    return agent


@app.get("/", include_in_schema=False)
def index():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend is not available.")
    return FileResponse(index_path)


@app.get("/health")
def health() -> dict:
    return {"status": "ok" if agent is not None else "loading", "ready": agent is not None}


@app.get("/stats")
def stats() -> dict:
    current_agent = get_agent()
    return {
        "chunk_count": chunks_count,
        "tools": current_agent.registry.tool_names(),
        "model": current_agent.generator.model_name,
        "trace_path": (
            str(current_agent.trace_store.trace_file)
            if current_agent.trace_store is not None
            else None
        ),
        "llm": current_agent.generator.config(),
    }


@app.get("/config")
def config() -> dict:
    current_agent = get_agent()
    return {
        "llm": current_agent.generator.config(),
        "agent": {
            "top_k": current_agent.config.top_k,
            "max_tool_retries": current_agent.config.max_tool_retries,
            "persist_traces": current_agent.config.persist_traces,
        },
    }


@app.get("/traces")
def traces(limit: int = 20) -> dict:
    current_agent = get_agent()
    if current_agent.trace_store is None:
        return {"traces": []}
    return {"traces": current_agent.trace_store.list_recent(limit=limit)}


@app.post("/agent", response_model=AgentResponse)
def run_agent(request: AgentRequest) -> dict:
    current_agent = get_agent()
    return current_agent.run(request.query, top_k=request.top_k)
