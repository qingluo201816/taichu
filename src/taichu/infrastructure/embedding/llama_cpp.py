"""通过 llama.cpp OpenAI 兼容接口调用本地 Qwen Embedding。"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx

from taichu.application.contracts.embedding import EmbeddingUsageRepository
from taichu.application.embeddings.models import (
    EmbeddingCallRecord,
    EmbeddingModelProfile,
    EmbeddingNormalization,
    EmbeddingPurpose,
    EmbeddingRequest,
    EmbeddingResponse,
)

_QUERY_INSTRUCTION = (
    "Instruct: 根据玄幻小说知识检索请求，检索能够回答请求的权威知识片段\n"
    "Query: "
)


class LlamaCppEmbeddingGateway:
    """校验真实向量响应并以最佳努力写入脱敏遥测。"""

    def __init__(
        self,
        *,
        base_url: str,
        model_id: str,
        dimensions: int,
        timeout_seconds: float,
        usage_repository: EmbeddingUsageRepository,
        max_input_tokens: int = 8192,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._dimensions = dimensions
        self._usage_repository = usage_repository
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds)
        )
        self._profile = EmbeddingModelProfile(
            model_id=model_id,
            dimensions=dimensions,
            max_input_tokens=max_input_tokens,
            supports_chinese=True,
            supports_multilingual=True,
            transport="openai_compatible_http",
            normalization=EmbeddingNormalization.L2,
        )

    def profile(self) -> EmbeddingModelProfile:
        return self._profile

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        call_id = f"embedding_{uuid4().hex}"
        started_at = _now_iso()
        timer = perf_counter()
        provider_request_id: str | None = None
        try:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                json={
                    "model": self._model_id,
                    "input": _transport_texts(request),
                    "encoding_format": "float",
                },
            )
            if response.status_code >= 400:
                raise _status_error(response.status_code)
            try:
                payload: Any = response.json()
            except (json.JSONDecodeError, httpx.DecodingError) as error:
                raise LlamaCppEmbeddingError(
                    "EMBEDDING_RESPONSE_INVALID",
                    "Embedding 服务返回了无法解析的响应。",
                ) from error
            provider_request_id = response.headers.get("x-request-id")
            vectors = _parse_vectors(payload, expected_count=len(request.texts))
            usage = payload.get("usage") if isinstance(payload, dict) else None
            input_tokens, total_tokens = _parse_usage(usage)
            result = EmbeddingResponse(
                call_id=call_id,
                model_id=self._model_id,
                dimensions=self._dimensions,
                normalization=EmbeddingNormalization.L2,
                vectors=vectors,
                input_tokens=input_tokens,
                total_tokens=total_tokens,
                duration_ms=_elapsed_ms(timer),
                provider_request_id=provider_request_id,
            )
        except Exception as error:
            safe = _normalize_error(error)
            await self._record(
                request=request,
                call_id=call_id,
                status="failed",
                started_at=started_at,
                timer=timer,
                error=safe,
                provider_request_id=provider_request_id,
            )
            raise safe from None

        await self._record(
            request=request,
            call_id=call_id,
            status="completed",
            started_at=started_at,
            timer=timer,
            response=result,
            provider_request_id=provider_request_id,
        )
        return result

    async def close(self) -> None:
        await self._client.aclose()

    async def _record(
        self,
        *,
        request: EmbeddingRequest,
        call_id: str,
        status: str,
        started_at: str,
        timer: float,
        response: EmbeddingResponse | None = None,
        error: LlamaCppEmbeddingError | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        record = EmbeddingCallRecord(
            call_id=call_id,
            run_id=request.run_id,
            invocation_id=request.invocation_id,
            purpose=request.purpose,
            model_role=request.model_role,
            model_id=self._model_id,
            dimensions=self._dimensions,
            normalization=EmbeddingNormalization.L2,
            text_count=len(request.texts),
            input_char_count=sum(len(text) for text in request.texts),
            input_sha256=_input_sha256(request.texts),
            input_tokens=response.input_tokens if response else None,
            total_tokens=response.total_tokens if response else None,
            status=status,  # type: ignore[arg-type]
            started_at=started_at,
            finished_at=_now_iso(),
            duration_ms=_elapsed_ms(timer),
            provider_request_id=provider_request_id,
            error_code=error.code if error else None,
            error_message=error.message if error else None,
        )
        try:
            await self._usage_repository.append(record)
        except Exception:  # noqa: BLE001
            return


class LlamaCppEmbeddingError(RuntimeError):
    """不包含输入原文、完整上游响应或本机敏感信息的稳定错误。"""

    def __init__(self, code: str, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _transport_texts(request: EmbeddingRequest) -> list[str]:
    if request.purpose is EmbeddingPurpose.KNOWLEDGE_QUERY:
        return [_QUERY_INSTRUCTION + text.strip() for text in request.texts]
    return [text.strip() for text in request.texts]


def _parse_vectors(payload: Any, *, expected_count: int) -> list[list[float]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise LlamaCppEmbeddingError(
            "EMBEDDING_RESPONSE_INVALID",
            "Embedding 服务返回的数据格式不正确。",
        )
    indexed: list[tuple[int, list[float]]] = []
    for position, item in enumerate(payload["data"]):
        if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
            raise LlamaCppEmbeddingError(
                "EMBEDDING_RESPONSE_INVALID",
                "Embedding 服务返回的数据格式不正确。",
            )
        try:
            vector = [float(value) for value in item["embedding"]]
        except (TypeError, ValueError) as error:
            raise LlamaCppEmbeddingError(
                "EMBEDDING_RESPONSE_INVALID",
                "Embedding 服务返回了非数值向量。",
            ) from error
        index = item.get("index", position)
        if not isinstance(index, int):
            raise LlamaCppEmbeddingError(
                "EMBEDDING_RESPONSE_INVALID",
                "Embedding 服务返回了无效向量序号。",
            )
        indexed.append((index, vector))
    indexed.sort(key=lambda pair: pair[0])
    if len(indexed) != expected_count or [item[0] for item in indexed] != list(
        range(expected_count)
    ):
        raise LlamaCppEmbeddingError(
            "EMBEDDING_COUNT_MISMATCH",
            "Embedding 服务返回的向量数量与输入不一致。",
        )
    return [vector for _, vector in indexed]


def _parse_usage(payload: Any) -> tuple[int | None, int | None]:
    if not isinstance(payload, dict):
        return None, None
    prompt_tokens = payload.get("prompt_tokens")
    total_tokens = payload.get("total_tokens")
    return (
        int(prompt_tokens) if isinstance(prompt_tokens, int | float) else None,
        int(total_tokens) if isinstance(total_tokens, int | float) else None,
    )


def _status_error(status_code: int) -> LlamaCppEmbeddingError:
    if status_code in {401, 403}:
        return LlamaCppEmbeddingError(
            "EMBEDDING_FORBIDDEN",
            "当前配置无权调用 Embedding 服务。",
            status_code=status_code,
        )
    if status_code == 429:
        return LlamaCppEmbeddingError(
            "EMBEDDING_RATE_LIMITED",
            "Embedding 服务当前繁忙，请稍后重试。",
            status_code=status_code,
        )
    if status_code >= 500:
        return LlamaCppEmbeddingError(
            "EMBEDDING_UPSTREAM_ERROR",
            "Embedding 服务暂时不可用。",
            status_code=status_code,
        )
    return LlamaCppEmbeddingError(
        "EMBEDDING_REQUEST_REJECTED",
        "Embedding 服务拒绝了本次请求。",
        status_code=status_code,
    )


def _normalize_error(error: Exception) -> LlamaCppEmbeddingError:
    if isinstance(error, LlamaCppEmbeddingError):
        return error
    if isinstance(error, httpx.TimeoutException):
        return LlamaCppEmbeddingError(
            "EMBEDDING_TIMEOUT", "Embedding 调用超时。"
        )
    if isinstance(error, httpx.NetworkError):
        return LlamaCppEmbeddingError(
            "EMBEDDING_NETWORK_ERROR", "无法连接本地 Embedding 服务。"
        )
    if isinstance(error, ValueError):
        return LlamaCppEmbeddingError(
            "EMBEDDING_RESPONSE_INVALID", "Embedding 响应未通过一致性校验。"
        )
    return LlamaCppEmbeddingError("EMBEDDING_CALL_FAILED", "Embedding 调用失败。")


def _input_sha256(texts: list[str]) -> str:
    payload = json.dumps(texts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _elapsed_ms(timer: float) -> int:
    return max(0, round((perf_counter() - timer) * 1000))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
