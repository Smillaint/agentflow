# -*- coding: utf-8 -*-
from __future__ import annotations

from src.schema import UsageStats


MODEL_PRICING_PER_1K = {
    "local-extractive": {"input": 0.0, "output": 0.0},
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.00060},
}


def estimate_tokens(text: str) -> int:
    """Cheap token estimate for local cost dashboards."""
    if not text:
        return 0
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii_chars // 2)


def estimate_usage(model: str, input_text: str, output_text: str) -> UsageStats:
    input_tokens = estimate_tokens(input_text)
    output_tokens = estimate_tokens(output_text)
    pricing = MODEL_PRICING_PER_1K.get(model, MODEL_PRICING_PER_1K["gpt-4o-mini"])
    estimated_cost = (
        input_tokens / 1000 * pricing["input"]
        + output_tokens / 1000 * pricing["output"]
    )
    return UsageStats(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd=estimated_cost,
        model=model,
    )


def usage_from_openai_response(model: str, response, fallback_input: str, answer: str) -> UsageStats:
    usage = getattr(response, "usage", None)
    if usage is None:
        return estimate_usage(model, fallback_input, answer)

    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", input_tokens + output_tokens) or 0
    pricing = MODEL_PRICING_PER_1K.get(model, MODEL_PRICING_PER_1K["gpt-4o-mini"])
    estimated_cost = (
        input_tokens / 1000 * pricing["input"]
        + output_tokens / 1000 * pricing["output"]
    )
    return UsageStats(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
        model=model,
    )

