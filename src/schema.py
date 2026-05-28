# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentChunk:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    chunk: DocumentChunk
    score: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    name: str
    output: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"name": self.name, "output": self.output}
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass
class UsageStats:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model: str = "local-extractive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 8),
            "model": self.model,
        }


@dataclass
class GenerationResult:
    answer: str
    usage: UsageStats
