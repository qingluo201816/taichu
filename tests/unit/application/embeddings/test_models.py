import math

import pytest
from pydantic import ValidationError

from taichu.application.embeddings.models import (
    EmbeddingNormalization,
    EmbeddingPurpose,
    EmbeddingRequest,
    EmbeddingResponse,
)


def test_request_rejects_empty_text_and_budget_overflow() -> None:
    with pytest.raises(ValidationError, match="空文本"):
        EmbeddingRequest(
            texts=[""],
            purpose=EmbeddingPurpose.KNOWLEDGE_DOCUMENT,
            input_char_budget=10,
        )
    with pytest.raises(ValidationError, match="字符预算"):
        EmbeddingRequest(
            texts=["超出预算"],
            purpose=EmbeddingPurpose.KNOWLEDGE_DOCUMENT,
            input_char_budget=3,
        )


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_response_rejects_non_finite_vectors(invalid: float) -> None:
    with pytest.raises(ValidationError, match="NaN 或 Infinity"):
        EmbeddingResponse(
            call_id="embedding_" + "a" * 32,
            model_id="local-model",
            dimensions=2,
            normalization=EmbeddingNormalization.L2,
            vectors=[[0.1, invalid]],
            duration_ms=1,
        )


def test_response_rejects_dimension_mismatch_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="维度不一致"):
        EmbeddingResponse(
            call_id="embedding_" + "a" * 32,
            model_id="local-model",
            dimensions=2,
            normalization=EmbeddingNormalization.L2,
            vectors=[[0.1]],
            duration_ms=1,
        )
    with pytest.raises(ValidationError):
        EmbeddingRequest.model_validate(
            {
                "texts": ["正文"],
                "purpose": "knowledge_document",
                "input_char_budget": 10,
                "unexpected": True,
            }
        )
