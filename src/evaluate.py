# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from main import load_local_env
from src.agent import AgentConfig, SingleAgent
from src.generator import build_generator
from src.loader import load_knowledge_base
from src.retriever import HybridRetriever
from src.tools import build_default_registry


def load_eval_cases(path: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not payload.get("question"):
                raise ValueError(f"Missing question at {path}:{line_number}")
            cases.append(payload)
    return cases


def build_agent(args) -> SingleAgent:
    chunks = load_knowledge_base(
        args.data_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    retriever = HybridRetriever(chunks)
    registry = build_default_registry(chunks, retriever)
    return SingleAgent(
        registry,
        build_generator(),
        AgentConfig(
            top_k=args.top_k,
            max_tool_retries=args.max_tool_retries,
            trace_dir=args.trace_dir,
            persist_traces=not args.no_persist_traces,
        ),
    )


def evaluate_case(agent: SingleAgent, case: dict[str, Any]) -> dict[str, Any]:
    started_at = time.perf_counter()
    result = agent.run(case["question"])
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    trace_text = json.dumps(result["trace"], ensure_ascii=False)
    answer_text = result["answer"]
    sources_text = json.dumps(result["sources"], ensure_ascii=False)
    combined_text = f"{answer_text}\n{sources_text}\n{trace_text}".lower()

    expected_tool = case.get("expected_tool")
    tool_hit = True
    if expected_tool:
        tool_hit = any(step.get("tool") == expected_tool for step in result["trace"])

    expected_keywords = case.get("expected_keywords", [])
    keyword_hits = {
        keyword: keyword.lower() in combined_text
        for keyword in expected_keywords
    }
    keyword_hit = all(keyword_hits.values())

    expected_sources = case.get("expected_sources", [])
    returned_sources = sorted(
        {
            str(source.get("source", ""))
            for source in result.get("sources", [])
            if isinstance(source, dict) and source.get("source")
        }
    )
    source_hits = {
        source: any(source.lower() in returned.lower() for returned in returned_sources)
        for source in expected_sources
    }
    source_hit = all(source_hits.values()) if expected_sources else True
    passed = tool_hit and keyword_hit and source_hit

    return {
        "question": case["question"],
        "passed": passed,
        "tool_hit": tool_hit,
        "keyword_hit": keyword_hit,
        "keyword_hits": keyword_hits,
        "source_hit": source_hit,
        "source_hits": source_hits,
        "expected_tool": expected_tool,
        "actual_tools": [step.get("tool") for step in result["trace"]],
        "returned_sources": returned_sources,
        "latency_ms": latency_ms,
        "usage": result.get("usage", {}),
        "run_id": result.get("run_id"),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate AgentFlow workflow quality.")
    parser.add_argument("--eval-file", default="./examples/eval_questions.jsonl")
    parser.add_argument("--data-dir", default="./examples/knowledge")
    parser.add_argument("--chunk-size", type=int, default=700)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--max-tool-retries", type=int, default=1)
    parser.add_argument("--trace-dir", default="./runs/eval_traces")
    parser.add_argument("--no-persist-traces", action="store_true")
    parser.add_argument("--report-file", default="")
    return parser.parse_args()


def main():
    load_local_env()
    args = parse_args()
    agent = build_agent(args)
    cases = load_eval_cases(args.eval_file)
    results = [evaluate_case(agent, case) for case in cases]
    passed = sum(1 for result in results if result["passed"])
    total_usage = {
        "input_tokens": sum(result.get("usage", {}).get("input_tokens", 0) for result in results),
        "output_tokens": sum(result.get("usage", {}).get("output_tokens", 0) for result in results),
        "total_tokens": sum(result.get("usage", {}).get("total_tokens", 0) for result in results),
        "estimated_cost_usd": round(
            sum(result.get("usage", {}).get("estimated_cost_usd", 0.0) for result in results),
            8,
        ),
    }
    avg_latency_ms = (
        sum(result["latency_ms"] for result in results) / len(results)
        if results
        else 0.0
    )
    report = {
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "avg_latency_ms": round(avg_latency_ms, 2),
        "total_usage": total_usage,
        "results": results,
    }

    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
