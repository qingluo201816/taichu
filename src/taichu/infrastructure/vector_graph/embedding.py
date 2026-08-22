"""为本地 OpenAI 兼容 Embedding 服务提供有界批处理。"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np


class BoundedEmbeddingModel:
    """限制单次请求文本量，超长文档池化后仍保持一个向量。"""

    def __init__(self, inner: Any, *, max_request_chars: int = 2_400) -> None:
        if max_request_chars < 256:
            raise ValueError("Embedding 单次请求字符上限不得小于 256。")
        self._inner = inner
        self.max_request_chars = max_request_chars

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int | None = None,
        show_progress: bool = False,
        text_type: Literal["query", "document"] = "query",
    ) -> list[list[float]]:
        del batch_size, show_progress
        if not texts:
            return []

        chunks_by_text = [
            _split_for_embedding(text, self.max_request_chars) for text in texts
        ]
        flat_chunks = [chunk for chunks in chunks_by_text for chunk in chunks]
        flat_embeddings: list[np.ndarray[Any, Any]] = []
        for batch in _bounded_batches(flat_chunks, self.max_request_chars):
            encoded = self._inner._backend.encode(batch, text_type=text_type)
            flat_embeddings.extend(np.asarray(item, dtype=float) for item in encoded)

        results: list[list[float]] = []
        offset = 0
        for chunks in chunks_by_text:
            vectors = flat_embeddings[offset : offset + len(chunks)]
            offset += len(chunks)
            pooled = np.mean(np.stack(vectors), axis=0)
            norm = float(np.linalg.norm(pooled))
            if norm > 0:
                pooled = pooled / norm
            results.append(pooled.tolist())
        return results


def _bounded_batches(texts: list[str], max_chars: int) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for text in texts:
        size = max(1, len(text))
        if current and current_chars + size > max_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(text)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def _split_for_embedding(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + max_chars)
        end = hard_end
        if hard_end < len(text):
            search_start = start + int(max_chars * 0.7)
            candidates = [
                text.rfind(separator, search_start, hard_end)
                for separator in ("\n\n", "\n", "。", "！", "？", "；")
            ]
            boundary = max(candidates)
            if boundary >= search_start:
                end = boundary + 1
        chunks.append(text[start:end])
        start = end
    return chunks
