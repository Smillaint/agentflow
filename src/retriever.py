# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import re
from collections import Counter

from src.schema import DocumentChunk, RetrievalResult


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


class BM25Retriever:
    """Small BM25 retriever for the MVP stage."""

    def __init__(self, chunks: list[DocumentChunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize(chunk.content) for chunk in chunks]
        self.doc_freq: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            self.doc_freq.update(set(tokens))
        self.avg_doc_len = (
            sum(len(tokens) for tokens in self.doc_tokens) / len(self.doc_tokens)
            if self.doc_tokens
            else 0.0
        )

    def _idf(self, token: str) -> float:
        total = len(self.doc_tokens)
        freq = self.doc_freq.get(token, 0)
        return math.log(1 + (total - freq + 0.5) / (freq + 0.5))

    def search(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        results: list[RetrievalResult] = []
        for chunk, tokens in zip(self.chunks, self.doc_tokens):
            token_counts = Counter(tokens)
            doc_len = len(tokens) or 1
            score = 0.0
            for token in query_tokens:
                freq = token_counts.get(token, 0)
                if freq == 0:
                    continue
                denominator = freq + self.k1 * (
                    1 - self.b + self.b * doc_len / (self.avg_doc_len or 1)
                )
                score += self._idf(token) * freq * (self.k1 + 1) / denominator
            if score > 0:
                results.append(RetrievalResult(chunk=chunk, score=score))

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

