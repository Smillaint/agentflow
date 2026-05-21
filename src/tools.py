# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.retriever import BM25Retriever
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


def _source_payload(chunk: DocumentChunk, score: float | None = None) -> dict[str, Any]:
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
    return payload


def build_default_registry(chunks: list[DocumentChunk], retriever: BM25Retriever) -> ToolRegistry:
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
                "sources": [_source_payload(item.chunk, item.score) for item in results],
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
            description="Search local knowledge chunks with BM25 retrieval.",
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

