# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.generator import AnswerGenerator
from src.tracing import TraceStore
from src.tools import ToolRegistry


@dataclass
class AgentConfig:
    top_k: int = 4
    max_tool_retries: int = 1
    trace_dir: str = "./runs/traces"
    persist_traces: bool = True


class SingleAgent:
    """One-agent workflow: route, call tools, generate answer, return trace."""

    def __init__(self, registry: ToolRegistry, generator: AnswerGenerator, config: AgentConfig):
        self.registry = registry
        self.generator = generator
        self.config = config
        self.trace_store = TraceStore(config.trace_dir) if config.persist_traces else None

    @staticmethod
    def _needs_stats(query: str) -> bool:
        normalized = query.lower()
        keywords = (
            "stats",
            "statistics",
            "how many",
            "source count",
            "chunk count",
            "统计",
            "多少",
            "文档数量",
            "来源",
        )
        return any(keyword in normalized for keyword in keywords)

    def _plan(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        if self._needs_stats(query):
            return [{"tool": "get_corpus_stats", "arguments": {}}]
        effective_top_k = top_k or self.config.top_k
        return [
            {
                "tool": "search_knowledge_base",
                "arguments": {"query": query, "top_k": effective_top_k},
            }
        ]

    def _execute_with_retries(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        max_attempts = self.config.max_tool_retries + 1
        last_result = None

        for attempt in range(1, max_attempts + 1):
            result = self.registry.execute(tool, arguments)
            last_result = result
            attempts.append({"attempt": attempt, "result": result.to_dict()})
            if result.error is None:
                break

        payload = last_result.to_dict() if last_result else {"name": tool, "output": {}}
        payload["attempts"] = attempts
        return payload

    @staticmethod
    def _collect_sources(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        seen: set[str] = set()
        for step in trace:
            output = step.get("result", {}).get("output", {})
            for source in output.get("sources", []):
                if not isinstance(source, dict):
                    continue
                chunk_id = str(source.get("chunk_id", source.get("source", "")))
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                sources.append(source)
        return sources

    def run(self, query: str, top_k: int | None = None) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        for index, call in enumerate(self._plan(query, top_k=top_k), start=1):
            result = self._execute_with_retries(call["tool"], call["arguments"])
            trace.append(
                {
                    "step": index,
                    "tool": call["tool"],
                    "arguments": call["arguments"],
                    "result": result,
                }
            )

        sources = self._collect_sources(trace)
        generation = self.generator.generate(query, sources, trace)
        result = {
            "answer": generation.answer,
            "trace": trace,
            "sources": sources,
            "usage": generation.usage.to_dict(),
        }
        if self.trace_store is not None:
            saved = self.trace_store.save({"query": query, **result})
            result["run_id"] = saved["run_id"]
            result["trace_path"] = str(self.trace_store.trace_file)
        return result
