# -*- coding: utf-8 -*-
import argparse
import json
import os
from pathlib import Path


def load_local_env(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs without overriding shell variables."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_args():
    parser = argparse.ArgumentParser(description="Run the AgentFlow MVP workflow.")
    parser.add_argument("query", nargs="?", help="Question to ask. If omitted, starts interactive mode.")
    parser.add_argument("--data-dir", default="./examples/knowledge", help="Directory containing knowledge files.")
    parser.add_argument("--chunk-size", type=int, default=700, help="Maximum characters per chunk.")
    parser.add_argument("--chunk-overlap", type=int, default=100, help="Overlapping characters between chunks.")
    parser.add_argument("--top-k", type=int, default=4, help="Number of chunks returned by retrieval.")
    parser.add_argument("--max-tool-retries", type=int, default=1, help="Retry count for failed tool calls.")
    parser.add_argument("--trace-dir", default="./runs/traces", help="Directory for JSONL trace records.")
    parser.add_argument("--no-persist-traces", action="store_true", help="Disable trace persistence.")
    parser.add_argument("--show-trace", action="store_true", help="Print tool-call trace as JSON.")
    return parser.parse_args()


def build_agent(args):
    from src.agent import AgentConfig, SingleAgent
    from src.generator import build_generator
    from src.loader import load_knowledge_base
    from src.retriever import HybridRetriever
    from src.tools import build_default_registry

    chunks = load_knowledge_base(
        args.data_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    retriever = HybridRetriever(chunks)
    registry = build_default_registry(chunks, retriever)
    generator = build_generator()
    return SingleAgent(
        registry,
        generator,
        AgentConfig(
            top_k=args.top_k,
            max_tool_retries=args.max_tool_retries,
            trace_dir=args.trace_dir,
            persist_traces=not args.no_persist_traces,
        ),
    )


def print_result(result: dict, show_trace: bool) -> None:
    print(result["answer"])
    if "usage" in result:
        print(f"\nUsage: {json.dumps(result['usage'], ensure_ascii=False)}")
    if "run_id" in result:
        print(f"Run ID: {result['run_id']}")
    if show_trace:
        print("\nTrace:")
        print(json.dumps(result["trace"], ensure_ascii=False, indent=2))


def main():
    load_local_env()
    args = parse_args()
    agent = build_agent(args)

    if args.query:
        print_result(agent.run(args.query), args.show_trace)
        return

    print("Enter a question, or type exit to quit.")
    while True:
        query = input("> ").strip()
        if query.lower() in {"exit", "quit", "q"}:
            break
        if not query:
            continue
        print_result(agent.run(query), args.show_trace)


if __name__ == "__main__":
    main()
