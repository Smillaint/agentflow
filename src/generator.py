# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from src.cost import estimate_usage, usage_from_openai_response
from src.schema import GenerationResult


class AnswerGenerator:
    def __init__(
        self,
        client=None,
        model_name: str = "local-extractive",
        base_url: str | None = None,
        provider: str = "local",
    ):
        self.client = client
        self.model_name = model_name
        self.base_url = base_url
        self.provider = provider

    @property
    def llm_enabled(self) -> bool:
        return self.client is not None

    def config(self) -> dict[str, Any]:
        return {
            "llm_enabled": self.llm_enabled,
            "model": self.model_name,
            "provider": self.provider,
            "base_url_host": _host_from_url(self.base_url),
        }

    def generate(
        self,
        query: str,
        sources: list[dict[str, Any]],
        trace: list[dict[str, Any]],
    ) -> GenerationResult:
        stats_answer = self._stats_answer(trace)
        if stats_answer:
            return GenerationResult(
                answer=stats_answer,
                usage=estimate_usage(self.model_name, query, stats_answer),
            )

        if self.client is None:
            return self._generate_local(query, sources, trace)

        try:
            return self._generate_with_model(query, sources)
        except Exception as exc:  # noqa: BLE001 - fallback is part of runtime reliability.
            trace.append(
                {
                    "step": len(trace) + 1,
                    "tool": "answer_generator",
                    "arguments": {
                        "model": self.model_name,
                        "provider": self.provider,
                    },
                    "result": {
                        "name": "answer_generator",
                        "output": {"fallback": "local-extractive"},
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                }
            )
            return self._generate_local(query, sources, trace, fallback_reason=str(exc))

    def _generate_local(
        self,
        query: str,
        sources: list[dict[str, Any]],
        trace: list[dict[str, Any]],
        fallback_reason: str | None = None,
    ) -> GenerationResult:
        if not sources:
            answer = "No sufficiently relevant content was found in the local knowledge base."
            if fallback_reason:
                answer = f"Model generation failed, so AgentFlow used local fallback.\n\n{answer}"
            return GenerationResult(
                answer=answer,
                usage=estimate_usage(self.model_name, query, answer),
            )

        lines = []
        if fallback_reason:
            lines.append("Model generation failed, so AgentFlow used local fallback.")
            lines.append("")
        lines.append("Retrieved evidence from the local knowledge base:")
        for index, source in enumerate(sources[:4], start=1):
            chunk_id = source.get("chunk_id", "unknown")
            preview = str(source.get("preview", "")).replace("\n", " ")
            lines.append(f"{index}. {preview} [{chunk_id}]")
        if self.client is None:
            lines.append("Set OPENAI_API_KEY to enable model-generated synthesis.")
        answer = "\n".join(lines)
        input_text = query + "\n" + "\n".join(str(source.get("content", "")) for source in sources)
        return GenerationResult(
            answer=answer,
            usage=estimate_usage(self.model_name, input_text, answer),
        )

    @staticmethod
    def _stats_answer(trace: list[dict[str, Any]]) -> str | None:
        for step in trace:
            if step.get("tool") != "get_corpus_stats":
                continue
            output = step.get("result", {}).get("output", {})
            if output:
                return (
                    "Knowledge base stats: "
                    f"source_count={output.get('source_count', 0)}, "
                    f"chunk_count={output.get('chunk_count', 0)}, "
                    f"sources={output.get('sources', [])}."
                )
        return None

    def _generate_with_model(
        self,
        query: str,
        sources: list[dict[str, Any]],
    ) -> GenerationResult:
        if not sources:
            answer = "No sufficiently relevant content was found in the local knowledge base."
            return GenerationResult(
                answer=answer,
                usage=estimate_usage(self.model_name, query, answer),
            )

        context = "\n\n".join(
            f"[{source.get('chunk_id', f'chunk-{index}')}] "
            f"source={source.get('source', 'unknown')}\n"
            f"{source.get('content', source.get('preview', ''))}"
            for index, source in enumerate(sources[:6], start=1)
        )
        user_content = (
            "Answer the question using only the sources below.\n\n"
            f"Question:\n{query}\n\n"
            f"Sources:\n{context}\n\n"
            "Required output:\n"
            "1. Direct answer.\n"
            "2. Evidence with cited chunk_id values.\n"
            "3. If the sources are insufficient, state exactly what is missing.\n"
        )
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are AgentFlow's grounded answer generator. You must answer "
                        "only from the retrieved sources. Do not use outside knowledge. "
                        "Cite chunk_id values exactly as provided, for example "
                        "[agentflow.md:c0]. If the answer cannot be fully supported, "
                        "say the evidence is insufficient and explain what source is missing. "
                        "Keep the answer concise, concrete, and interview-ready."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        answer = response.choices[0].message.content or ""
        return GenerationResult(
            answer=answer,
            usage=usage_from_openai_response(self.model_name, response, user_content, answer),
        )


def build_generator() -> AnswerGenerator:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return AnswerGenerator()

    from openai import OpenAI

    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    provider = _infer_provider(base_url, model)
    client = (
        OpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
        if base_url
        else OpenAI(api_key=api_key, timeout=30.0)
    )
    return AnswerGenerator(
        client=client,
        model_name=model,
        base_url=base_url,
        provider=provider,
    )


def _host_from_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    parsed = urlparse(base_url)
    return parsed.netloc or parsed.path.split("/")[0]


def _infer_provider(base_url: str | None, model: str) -> str:
    host = (_host_from_url(base_url) or "").lower()
    model_name = model.lower()
    if "deepseek" in host or "deepseek" in model_name:
        return "deepseek"
    if "openai" in host or model_name.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if not base_url:
        return "openai"
    return "openai-compatible"
