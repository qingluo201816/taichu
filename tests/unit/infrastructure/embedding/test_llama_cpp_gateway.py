from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from taichu.application.embeddings.models import (
    EmbeddingCallRecord,
    EmbeddingPurpose,
    EmbeddingRequest,
)
from taichu.infrastructure.embedding.llama_cpp import (
    LlamaCppEmbeddingError,
    LlamaCppEmbeddingGateway,
)


class _UsageRepository:
    def __init__(self) -> None:
        self.records: list[EmbeddingCallRecord] = []

    async def append(self, record: EmbeddingCallRecord) -> None:
        self.records.append(record)


def test_calls_openai_compatible_endpoint_and_records_no_content() -> None:
    asyncio.run(_calls_openai_compatible_endpoint_and_records_no_content())


async def _calls_openai_compatible_endpoint_and_records_no_content() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-request-id": "local-request"},
            json={
                "data": [
                    {"index": 0, "embedding": [0.6, 0.8]},
                    {"index": 1, "embedding": [0.0, 1.0]},
                ],
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            },
        )

    repository = _UsageRepository()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = LlamaCppEmbeddingGateway(
            base_url="http://127.0.0.1:8011/v1",
            model_id="Qwen3-Embedding-4B-Q4_K_M",
            dimensions=2,
            timeout_seconds=1,
            usage_repository=repository,
            client=client,
        )
        response = await gateway.embed(
            EmbeddingRequest(
                texts=["谁来自翔龙国？", "哪个宗门位于大屿山？"],
                purpose=EmbeddingPurpose.KNOWLEDGE_QUERY,
                input_char_budget=100,
                run_id="evaluation",
            )
        )

    assert str(captured["input"][0]).startswith("Instruct:")  # type: ignore[index]
    assert response.vectors == [[0.6, 0.8], [0.0, 1.0]]
    assert response.input_tokens == 5
    assert repository.records[0].status == "completed"
    serialized = repository.records[0].model_dump_json()
    assert "谁来自翔龙国" not in serialized
    assert "0.6" not in serialized


def test_rejects_wrong_vector_count_with_safe_error() -> None:
    asyncio.run(_rejects_wrong_vector_count_with_safe_error())


async def _rejects_wrong_vector_count_with_safe_error() -> None:
    repository = _UsageRepository()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = LlamaCppEmbeddingGateway(
            base_url="http://127.0.0.1:8011/v1",
            model_id="local-model",
            dimensions=2,
            timeout_seconds=1,
            usage_repository=repository,
            client=client,
        )
        with pytest.raises(LlamaCppEmbeddingError) as captured:
            await gateway.embed(
                EmbeddingRequest(
                    texts=["正文"],
                    purpose=EmbeddingPurpose.KNOWLEDGE_DOCUMENT,
                    input_char_budget=10,
                )
            )

    assert captured.value.code == "EMBEDDING_COUNT_MISMATCH"
    assert repository.records[0].status == "failed"
    assert repository.records[0].error_code == "EMBEDDING_COUNT_MISMATCH"


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (403, "EMBEDDING_FORBIDDEN"),
        (429, "EMBEDDING_RATE_LIMITED"),
        (503, "EMBEDDING_UPSTREAM_ERROR"),
    ],
)
def test_maps_http_failures_to_safe_codes(
    status_code: int,
    expected_code: str,
) -> None:
    async def scenario() -> None:
        repository = _UsageRepository()

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, text="sensitive upstream body")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            gateway = LlamaCppEmbeddingGateway(
                base_url="http://127.0.0.1:8011/v1",
                model_id="local-model",
                dimensions=2,
                timeout_seconds=1,
                usage_repository=repository,
                client=client,
            )
            with pytest.raises(LlamaCppEmbeddingError) as captured:
                await gateway.embed(
                    EmbeddingRequest(
                        texts=["正文"],
                        purpose=EmbeddingPurpose.KNOWLEDGE_DOCUMENT,
                        input_char_budget=10,
                    )
                )

        assert captured.value.code == expected_code
        assert "sensitive upstream body" not in str(captured.value)
        assert repository.records[0].error_code == expected_code

    asyncio.run(scenario())


def test_maps_timeout_to_safe_code() -> None:
    async def scenario() -> None:
        repository = _UsageRepository()

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("sensitive timeout", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            gateway = LlamaCppEmbeddingGateway(
                base_url="http://127.0.0.1:8011/v1",
                model_id="local-model",
                dimensions=2,
                timeout_seconds=1,
                usage_repository=repository,
                client=client,
            )
            with pytest.raises(LlamaCppEmbeddingError) as captured:
                await gateway.embed(
                    EmbeddingRequest(
                        texts=["正文"],
                        purpose=EmbeddingPurpose.KNOWLEDGE_DOCUMENT,
                        input_char_budget=10,
                    )
                )

        assert captured.value.code == "EMBEDDING_TIMEOUT"
        assert repository.records[0].error_code == "EMBEDDING_TIMEOUT"

    asyncio.run(scenario())
