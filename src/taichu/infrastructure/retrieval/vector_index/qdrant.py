"""Qdrant Server 的向量索引后端实现。"""

from __future__ import annotations

from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from taichu.application.retrieval.vector_index_models import (
    VectorIndexCollectionState,
    VectorIndexPoint,
    VectorIndexSearchHit,
    VectorIndexSearchRequest,
)


class QdrantVectorIndexBackend:
    """只在 Qdrant 保存向量及定位载荷，不保存完整知识卡。"""

    def __init__(
        self,
        *,
        url: str,
        api_key: str = "",
        timeout_seconds: float = 30,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self._client = client or AsyncQdrantClient(
            url=url,
            api_key=api_key or None,
            timeout=max(1, round(timeout_seconds)),
            prefer_grpc=False,
        )

    async def create_collection(
        self,
        collection_name: str,
        *,
        dimensions: int,
    ) -> None:
        try:
            if await self._client.collection_exists(collection_name):
                raise VectorIndexBackendError(
                    "VECTOR_COLLECTION_EXISTS",
                    "目标向量物理集合已经存在。",
                )
            created = await self._client.create_collection(
                collection_name,
                vectors_config=qmodels.VectorParams(
                    size=dimensions,
                    distance=qmodels.Distance.COSINE,
                ),
                on_disk_payload=True,
            )
            if not created:
                raise VectorIndexBackendError(
                    "VECTOR_COLLECTION_CREATE_FAILED",
                    "Qdrant 未确认向量集合创建成功。",
                )
            for field_name in ("source_lifecycle", "knowledge_type"):
                await self._client.create_payload_index(
                    collection_name,
                    field_name=field_name,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
        except Exception as error:
            raise _normalize_error(error, "VECTOR_COLLECTION_CREATE_FAILED") from None

    async def upsert_points(
        self,
        collection_name: str,
        points: list[VectorIndexPoint],
    ) -> None:
        if not points:
            return
        try:
            await self._client.upsert(
                collection_name,
                points=[
                    qmodels.PointStruct(
                        id=point.point_id,
                        vector=point.vector,
                        payload=point.payload,
                    )
                    for point in points
                ],
                wait=True,
            )
        except Exception as error:
            raise _normalize_error(error, "VECTOR_UPSERT_FAILED") from None

    async def collection_state(
        self,
        collection_name: str,
    ) -> VectorIndexCollectionState | None:
        try:
            if not await self._client.collection_exists(collection_name):
                return None
            info = await self._client.get_collection(collection_name)
            vectors = info.config.params.vectors
            if not isinstance(vectors, qmodels.VectorParams):
                raise VectorIndexBackendError(
                    "VECTOR_COLLECTION_INVALID",
                    "Qdrant 集合不是预期的单向量配置。",
                )
            count = await self._client.count(collection_name, exact=True)
            if vectors.distance is not qmodels.Distance.COSINE:
                raise VectorIndexBackendError(
                    "VECTOR_COLLECTION_INVALID",
                    "Qdrant 集合距离类型不是 Cosine。",
                )
            return VectorIndexCollectionState(
                collection_name=collection_name,
                point_count=count.count,
                dimensions=vectors.size,
            )
        except Exception as error:
            raise _normalize_error(error, "VECTOR_COLLECTION_READ_FAILED") from None

    async def get_alias_target(self, alias_name: str) -> str | None:
        try:
            aliases = await self._client.get_aliases()
            matched = [
                item.collection_name
                for item in aliases.aliases
                if item.alias_name == alias_name
            ]
            if len(matched) > 1:
                raise VectorIndexBackendError(
                    "VECTOR_ALIAS_INVALID",
                    "Qdrant active alias 指向了多个集合。",
                )
            return matched[0] if matched else None
        except Exception as error:
            raise _normalize_error(error, "VECTOR_ALIAS_READ_FAILED") from None

    async def replace_alias(
        self,
        alias_name: str,
        collection_name: str | None,
    ) -> None:
        current = await self.get_alias_target(alias_name)
        if current == collection_name:
            return
        operations: list[
            qmodels.CreateAliasOperation | qmodels.DeleteAliasOperation
        ] = []
        if current is not None:
            operations.append(
                qmodels.DeleteAliasOperation(
                    delete_alias=qmodels.DeleteAlias(alias_name=alias_name)
                )
            )
        if collection_name is not None:
            operations.append(
                qmodels.CreateAliasOperation(
                    create_alias=qmodels.CreateAlias(
                        collection_name=collection_name,
                        alias_name=alias_name,
                    )
                )
            )
        if not operations:
            return
        try:
            updated = await self._client.update_collection_aliases(operations)
            if not updated:
                raise VectorIndexBackendError(
                    "VECTOR_ALIAS_SWITCH_FAILED",
                    "Qdrant 未确认 active alias 切换成功。",
                )
        except Exception as error:
            raise _normalize_error(error, "VECTOR_ALIAS_SWITCH_FAILED") from None

    async def delete_collection(self, collection_name: str) -> None:
        try:
            if await self._client.collection_exists(collection_name):
                await self._client.delete_collection(collection_name)
        except Exception as error:
            raise _normalize_error(error, "VECTOR_COLLECTION_DELETE_FAILED") from None

    async def search(
        self,
        request: VectorIndexSearchRequest,
    ) -> list[VectorIndexSearchHit]:
        conditions: list[qmodels.Condition] = [
            qmodels.FieldCondition(
                key="source_lifecycle",
                match=qmodels.MatchValue(value="confirmed"),
            )
        ]
        if request.knowledge_types:
            conditions.append(
                qmodels.FieldCondition(
                    key="knowledge_type",
                    match=qmodels.MatchAny(
                        any=sorted(item.value for item in request.knowledge_types)
                    ),
                )
            )
        try:
            response = await self._client.query_points(
                request.collection_name,
                query=request.vector,
                query_filter=qmodels.Filter(must=conditions),
                limit=request.top_k,
                with_payload=True,
                with_vectors=False,
                score_threshold=request.score_threshold,
            )
            return [_parse_hit(point) for point in response.points]
        except Exception as error:
            raise _normalize_error(error, "VECTOR_SEARCH_FAILED") from None

    async def close(self) -> None:
        await self._client.close()


class VectorIndexBackendError(RuntimeError):
    """不泄露 Qdrant 连接细节和原始载荷的稳定错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _parse_hit(point: Any) -> VectorIndexSearchHit:
    payload = point.payload
    if not isinstance(payload, dict):
        raise VectorIndexBackendError(
            "VECTOR_PAYLOAD_INVALID", "Qdrant 命中缺少可追溯载荷。"
        )
    try:
        return VectorIndexSearchHit(
            point_id=str(point.id),
            score=float(point.score),
            card_id=payload["card_id"],
            knowledge_type=payload["knowledge_type"],
            document_kind=payload["document_kind"],
            field_paths=payload["field_paths"],
            content_sha256=payload["content_sha256"],
            card_updated_at=payload["card_updated_at"],
            source_lifecycle=payload["source_lifecycle"],
            projection_strategy_id=payload["projection_strategy_id"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise VectorIndexBackendError(
            "VECTOR_PAYLOAD_INVALID", "Qdrant 命中载荷未通过一致性校验。"
        ) from error


def _normalize_error(error: Exception, fallback_code: str) -> VectorIndexBackendError:
    if isinstance(error, VectorIndexBackendError):
        return error
    return VectorIndexBackendError(fallback_code, "Qdrant 向量索引操作失败。")
