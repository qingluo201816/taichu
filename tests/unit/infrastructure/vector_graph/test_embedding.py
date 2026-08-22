from types import SimpleNamespace

import numpy as np
import pytest

from taichu.infrastructure.vector_graph.embedding import BoundedEmbeddingModel


class _Backend:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str], *, text_type: str) -> np.ndarray:
        assert text_type == "document"
        self.calls.append(texts)
        return np.asarray([[float(len(text)), 1.0] for text in texts])


def test_long_document_is_pooled_into_one_normalized_vector() -> None:
    backend = _Backend()
    inner = SimpleNamespace(_backend=backend, dimension=2)
    model = BoundedEmbeddingModel(inner, max_request_chars=256)

    vectors = model.embed_batch(["甲" * 700, "乙" * 20], text_type="document")

    assert len(vectors) == 2
    assert all(len(vector) == 2 for vector in vectors)
    assert len(backend.calls) == 3
    assert all(sum(len(text) for text in call) <= 256 for call in backend.calls)
    assert np.linalg.norm(vectors[0]) == pytest.approx(1.0)


def test_short_texts_share_bounded_requests() -> None:
    backend = _Backend()
    inner = SimpleNamespace(_backend=backend, dimension=2)
    model = BoundedEmbeddingModel(inner, max_request_chars=256)

    model.embed_batch(["甲" * 100, "乙" * 100, "丙" * 100], text_type="document")

    assert [len(call) for call in backend.calls] == [2, 1]
