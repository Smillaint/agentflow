# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.agent import AgentConfig, SingleAgent
from src.generator import AnswerGenerator
from src.loader import load_knowledge_base
from src.retriever import BM25Retriever
from src.schema import ToolResult
from src.tools import build_default_registry


class AgentWorkflowTest(unittest.TestCase):
    def build_agent(self) -> SingleAgent:
        chunks = load_knowledge_base("./examples/knowledge")
        retriever = BM25Retriever(chunks)
        registry = build_default_registry(chunks, retriever)
        return SingleAgent(
            registry,
            AnswerGenerator(),
            AgentConfig(top_k=3, persist_traces=False),
        )

    def test_search_workflow_returns_trace_sources_and_usage(self):
        agent = self.build_agent()
        result = agent.run("AgentFlow stage one capabilities")

        self.assertTrue(result["answer"])
        self.assertEqual(result["trace"][0]["tool"], "search_knowledge_base")
        self.assertGreaterEqual(len(result["sources"]), 1)
        self.assertIn("usage", result)

    def test_stats_workflow_uses_stats_tool(self):
        agent = self.build_agent()
        result = agent.run("knowledge base stats")

        self.assertEqual(result["trace"][0]["tool"], "get_corpus_stats")
        output = result["trace"][0]["result"]["output"]
        self.assertGreaterEqual(output["chunk_count"], 1)
        self.assertGreaterEqual(output["source_count"], 1)
        self.assertEqual(result["usage"]["model"], "local-extractive")

    def test_trace_persistence_adds_run_metadata(self):
        chunks = load_knowledge_base("./examples/knowledge")
        retriever = BM25Retriever(chunks)
        registry = build_default_registry(chunks, retriever)
        with TemporaryDirectory() as trace_dir:
            agent = SingleAgent(
                registry,
                AnswerGenerator(),
                AgentConfig(top_k=2, trace_dir=trace_dir),
            )
            result = agent.run("AgentFlow capabilities")

            self.assertIn("run_id", result)
            self.assertIn("trace_path", result)

    def test_failed_tool_is_retried(self):
        class FlakyRegistry:
            def __init__(self):
                self.calls = 0

            def execute(self, name, arguments):
                self.calls += 1
                if self.calls == 1:
                    return ToolResult(name=name, output={}, error="temporary failure")
                return ToolResult(
                    name=name,
                    output={
                        "sources": [
                            {
                                "chunk_id": "fake:c0",
                                "preview": "recovered",
                                "content": "recovered content",
                            }
                        ]
                    },
                )

        agent = SingleAgent(
            FlakyRegistry(),
            AnswerGenerator(),
            AgentConfig(max_tool_retries=1, persist_traces=False),
        )
        result = agent.run("recoverable question")

        attempts = result["trace"][0]["result"]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(result["sources"]), 1)

    def test_model_failure_falls_back_to_local_answer(self):
        class BrokenCompletions:
            def create(self, **kwargs):
                raise RuntimeError("model unavailable")

        class BrokenClient:
            chat = type("Chat", (), {"completions": BrokenCompletions()})()

        chunks = load_knowledge_base("./examples/knowledge")
        retriever = BM25Retriever(chunks)
        registry = build_default_registry(chunks, retriever)
        agent = SingleAgent(
            registry,
            AnswerGenerator(
                client=BrokenClient(),
                model_name="deepseek-chat",
                base_url="https://api.deepseek.com",
                provider="deepseek",
            ),
            AgentConfig(persist_traces=False),
        )
        result = agent.run("What did stage two add?")

        self.assertIn("Model generation failed", result["answer"])
        self.assertEqual(result["trace"][-1]["tool"], "answer_generator")
        self.assertIn("error", result["trace"][-1]["result"])

    def test_pdf_knowledge_file_is_loaded_with_page_metadata(self):
        import fitz

        with TemporaryDirectory() as data_dir:
            pdf_path = Path(data_dir) / "guide.pdf"
            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_text((72, 72), "PDF knowledge base content for AgentFlow.")
            pdf.save(str(pdf_path))
            pdf.close()

            chunks = load_knowledge_base(data_dir, chunk_size=200, chunk_overlap=20)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["source"], "guide.pdf")
        self.assertEqual(chunks[0].metadata["page"], 1)
        self.assertEqual(chunks[0].metadata["chunk_id"], "guide.pdf:p1:c0")
        self.assertIn("PDF knowledge base content", chunks[0].content)


if __name__ == "__main__":
    unittest.main()
