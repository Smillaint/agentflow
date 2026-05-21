# AgentFlow Project Overview

AgentFlow is a single-agent workflow project for enterprise knowledge bases.
Stage one includes local knowledge loading, BM25 retrieval, tool calling, answer
generation, and trace output.

The goal is not just to complete one chat response. The system preserves tool
calls, retrieval sources, intermediate states, and usage statistics so later
stages can add observability, automated evaluation, replay, and cost control.

Stage one provides two built-in tools:

- search_knowledge_base: retrieve relevant chunks from the local knowledge base.
- get_corpus_stats: report source count and chunk count for the loaded corpus.

Stage two adds JSONL trace persistence, automated eval cases, tool failure
retry, token and cost estimation, and a trace API for recent runs.

Future stages can extend this into a multi-agent state machine, trace-level
evaluation, model routing, budget control, failure recovery, and human approval.
