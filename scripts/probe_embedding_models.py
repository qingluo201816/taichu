"""使用固定中文语义样例安全探测本地 Embedding 能力。"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

from taichu.application.embeddings.models import EmbeddingPurpose, EmbeddingRequest
from taichu.config import Settings
from taichu.infrastructure.embedding import LlamaCppEmbeddingGateway


class _DiscardUsageRepository:
    async def append(self, record: object) -> None:
        return


async def _run() -> int:
    settings = Settings()
    gateway = LlamaCppEmbeddingGateway(
        base_url=settings.embedding_base_url,
        model_id=settings.embedding_model_id,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.embedding_request_timeout_seconds,
        usage_repository=_DiscardUsageRepository(),  # type: ignore[arg-type]
        max_input_tokens=settings.embedding_max_input_tokens,
    )
    try:
        response = await gateway.embed(
            EmbeddingRequest(
                texts=[
                    "翔龙国皇帝最疼爱的三皇子是谁？",
                    "李靖是翔龙国皇帝最疼爱的三皇子。",
                    "绝仙毒谷是万毒魔尊自爆后形成的危险禁地。",
                ],
                purpose=EmbeddingPurpose.KNOWLEDGE_QUERY,
                input_char_budget=1_000,
                run_id="embedding_probe",
            )
        )
        related = _cosine(response.vectors[0], response.vectors[1])
        unrelated = _cosine(response.vectors[0], response.vectors[2])
        _print_json(
            {
                "status": "ok",
                "endpoint": settings.embedding_base_url,
                "model_id": response.model_id,
                "dimensions": response.dimensions,
                "vector_count": len(response.vectors),
                "normalization": response.normalization.value,
                "duration_ms": response.duration_ms,
                "related_cosine": round(related, 6),
                "unrelated_cosine": round(unrelated, 6),
                "finite": all(
                    math.isfinite(value)
                    for vector in response.vectors
                    for value in vector
                ),
            }
        )
        return 0
    finally:
        await gateway.close()


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
