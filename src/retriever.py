# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from src.schema import DocumentChunk, RetrievalResult


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _normalize_scores(scores: dict[int, float]) -> dict[int, float]:
    if not scores:
        return {}
    max_score = max(scores.values())
    if max_score <= 0:
        return {index: 0.0 for index in scores}
    return {index: score / max_score for index, score in scores.items()}


class BM25Retriever:
    """BM25 keyword retriever for exact terms, acronyms, and code-like queries."""

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

    def score_all(self, query: str) -> dict[int, float]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return {}

        scores: dict[int, float] = {}
        for index, tokens in enumerate(self.doc_tokens):
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
                scores[index] = score
        return scores

    def search(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        scores = self.score_all(query)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            RetrievalResult(
                chunk=self.chunks[index],
                score=score,
                details={"bm25_raw": score, "retrieval_mode": "bm25"},
            )
            for index, score in ranked
        ]


class NgramTfidfRetriever:
    """Dependency-free lexical vector retriever using word tokens and char n-grams."""

    def __init__(self, chunks: list[DocumentChunk], ngram_range: tuple[int, int] = (2, 3)):
        self.chunks = chunks
        self.ngram_range = ngram_range
        self.doc_vectors = [self._vectorize_tokens(self._tokens(chunk.content)) for chunk in chunks]
        self.doc_freq: Counter[str] = Counter()
        for vector in self.doc_vectors:
            self.doc_freq.update(vector.keys())
        self.idf = {
            token: math.log(1 + (len(chunks) + 1) / (freq + 1))
            for token, freq in self.doc_freq.items()
        }
        self.tfidf_vectors = [self._to_tfidf(vector) for vector in self.doc_vectors]
        self.norms = [math.sqrt(sum(value * value for value in vector.values())) for vector in self.tfidf_vectors]

    def _tokens(self, text: str) -> list[str]:
        base_tokens = tokenize(text)
        compact = "".join(base_tokens)
        ngrams: list[str] = []
        for size in range(self.ngram_range[0], self.ngram_range[1] + 1):
            if len(compact) < size:
                continue
            ngrams.extend(compact[index : index + size] for index in range(len(compact) - size + 1))
        return base_tokens + ngrams

    @staticmethod
    def _vectorize_tokens(tokens: list[str]) -> Counter[str]:
        return Counter(tokens)

    def _to_tfidf(self, vector: Counter[str]) -> dict[str, float]:
        if not vector:
            return {}
        max_tf = max(vector.values())
        return {
            token: (freq / max_tf) * self.idf.get(token, 0.0)
            for token, freq in vector.items()
        }

    def score_all(self, query: str) -> dict[int, float]:
        query_vector = self._to_tfidf(self._vectorize_tokens(self._tokens(query)))
        query_norm = math.sqrt(sum(value * value for value in query_vector.values()))
        if not query_vector or query_norm == 0:
            return {}

        scores: dict[int, float] = {}
        for index, doc_vector in enumerate(self.tfidf_vectors):
            doc_norm = self.norms[index]
            if doc_norm == 0:
                continue
            dot = sum(query_vector.get(token, 0.0) * value for token, value in doc_vector.items())
            score = dot / (query_norm * doc_norm)
            if score > 0:
                scores[index] = score
        return scores

    def search(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        scores = self.score_all(query)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            RetrievalResult(
                chunk=self.chunks[index],
                score=score,
                details={"vector_raw": score, "retrieval_mode": "ngram_tfidf"},
            )
            for index, score in ranked
        ]


class HybridRetriever:
    """BM25 + lexical vector fusion with score explanation for each returned chunk."""

    def __init__(
        self,
        chunks: list[DocumentChunk],
        bm25_weight: float = 0.65,
        vector_weight: float = 0.35,
    ):
        self.chunks = chunks
        self.bm25 = BM25Retriever(chunks)
        self.vector = NgramTfidfRetriever(chunks)
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight

    def search(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        bm25_scores = self.bm25.score_all(query)
        vector_scores = self.vector.score_all(query)
        bm25_norm = _normalize_scores(bm25_scores)
        vector_norm = _normalize_scores(vector_scores)
        candidate_indices = set(bm25_scores) | set(vector_scores)

        fused_scores: dict[int, float] = {}
        details: dict[int, dict[str, float | str]] = defaultdict(dict)
        for index in candidate_indices:
            score = (
                self.bm25_weight * bm25_norm.get(index, 0.0)
                + self.vector_weight * vector_norm.get(index, 0.0)
            )
            fused_scores[index] = score
            details[index] = {
                "retrieval_mode": "hybrid_bm25_ngram_tfidf",
                "bm25_raw": round(bm25_scores.get(index, 0.0), 6),
                "bm25_norm": round(bm25_norm.get(index, 0.0), 6),
                "vector_raw": round(vector_scores.get(index, 0.0), 6),
                "vector_norm": round(vector_norm.get(index, 0.0), 6),
                "bm25_weight": self.bm25_weight,
                "vector_weight": self.vector_weight,
            }

        ranked = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            RetrievalResult(
                chunk=self.chunks[index],
                score=score,
                details=dict(details[index]),
            )
            for index, score in ranked
        ]
