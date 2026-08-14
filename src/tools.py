# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.mcp_client import MCPClient
from src.schema import DocumentChunk, ToolResult


ToolHandler = Callable[[dict[str, Any]], ToolResult]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name=name, output={}, error=f"Unknown tool: {name}")
        try:
            return tool.handler(arguments)
        except Exception as exc:  # noqa: BLE001 - tool failures belong in the trace.
            return ToolResult(name=name, output={}, error=f"{type(exc).__name__}: {exc}")


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _source_payload(
    chunk: DocumentChunk,
    score: float | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "source": chunk.metadata.get("source"),
        "chunk_id": chunk.metadata.get("chunk_id"),
        "chunk_index": chunk.metadata.get("chunk_index"),
        "char_start": chunk.metadata.get("char_start"),
        "char_end": chunk.metadata.get("char_end"),
        "preview": chunk.content[:220],
        "content": chunk.content,
    }
    if score is not None:
        payload["score"] = round(score, 4)
    if details:
        payload["score_details"] = details
    return payload


def build_default_registry(chunks: list[DocumentChunk], retriever) -> ToolRegistry:
    registry = ToolRegistry()

    def search_knowledge_base(arguments: dict[str, Any]) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        top_k = _as_int(arguments.get("top_k"), 4, 1, 20)
        if not query:
            return ToolResult(
                name="search_knowledge_base",
                output={"sources": []},
                error="query is required",
            )
        results = retriever.search(query, top_k=top_k)
        return ToolResult(
            name="search_knowledge_base",
            output={
                "query": query,
                "top_k": top_k,
                "retrieval_mode": (
                    results[0].details.get("retrieval_mode")
                    if results and results[0].details
                    else "unknown"
                ),
                "sources": [
                    _source_payload(item.chunk, item.score, item.details)
                    for item in results
                ],
            },
        )

    def get_corpus_stats(arguments: dict[str, Any]) -> ToolResult:
        sources = sorted({str(chunk.metadata.get("source")) for chunk in chunks})
        return ToolResult(
            name="get_corpus_stats",
            output={
                "chunk_count": len(chunks),
                "source_count": len(sources),
                "sources": sources,
            },
        )

    registry.register(
        ToolSpec(
            name="search_knowledge_base",
            description="Search local knowledge chunks with hybrid BM25 and n-gram TF-IDF retrieval.",
            parameters={"query": "string", "top_k": "integer"},
            handler=search_knowledge_base,
        )
    )
    registry.register(
        ToolSpec(
            name="get_corpus_stats",
            description="Return loaded source and chunk statistics.",
            parameters={},
            handler=get_corpus_stats,
        )
    )
    return registry


def build_mcp_registry(client: MCPClient) -> ToolRegistry:
    """Build a ToolRegistry backed by a remote TraceRAG MCP server.

    Tool names deliberately match :func:`build_default_registry`
    (``search_knowledge_base`` and ``get_corpus_stats``) so that
    :class:`src.agent.SingleAgent` routing works unchanged. Retrieval
    delegates to TraceRAG's hybrid vector + BM25 (RRF) + HyDE +
    CrossEncoder reranking pipeline over MCP.
    """
    registry = ToolRegistry()

    def search_knowledge_base(arguments: dict[str, Any]) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        top_k = _as_int(arguments.get("top_k"), 4, 1, 20)
        collection = arguments.get("collection")
        if not query:
            return ToolResult(
                name="search_knowledge_base",
                output={"sources": []},
                error="query is required",
            )
        result = client.call_tool(
            "rag_search",
            {
                "query": query,
                "retrieve_top_k": max(top_k, 5),
                "rerank_top_k": top_k,
                "collection": collection,
            },
        )
        if "error" in result:
            return ToolResult(
                name="search_knowledge_base",
                output={"sources": []},
                error=result["error"],
            )
        sources = result.get("sources", [])
        return ToolResult(
            name="search_knowledge_base",
            output={
                "query": query,
                "top_k": top_k,
                "retrieval_mode": "mcp_tracerag_hybrid",
                "collection": collection,
                "sources": sources,
                "retrieval_trace": result.get("trace"),
                "source_count": result.get("source_count", len(sources)),
            },
        )

    def get_corpus_stats(arguments: dict[str, Any]) -> ToolResult:
        result = client.call_tool("rag_corpus_stats", {})
        if "error" in result:
            return ToolResult(name="get_corpus_stats", output={}, error=result["error"])
        return ToolResult(
            name="get_corpus_stats",
            output={
                "chunk_count": result.get("chunk_count", 0),
                "source_count": result.get("source_count", 0),
                "sources": result.get("sources", []),
                "collections": result.get("collections", []),
                "embedding_model": result.get("embedding_model"),
                "generation_model": result.get("generation_model"),
            },
        )

    registry.register(
        ToolSpec(
            name="search_knowledge_base",
            description="Search the TraceRAG PDF knowledge base via MCP: vector + BM25 hybrid (RRF), HyDE, CrossEncoder reranking.",
            parameters={"query": "string", "top_k": "integer", "collection": "string|None"},
            handler=search_knowledge_base,
        )
    )
    registry.register(
        ToolSpec(
            name="get_corpus_stats",
            description="Return corpus, chunk, and model statistics from the TraceRAG backend via MCP.",
            parameters={},
            handler=get_corpus_stats,
        )
    )
    return registry
