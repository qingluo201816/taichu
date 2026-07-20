"""从 MongoDB confirmed 知识卡全量重建并校验 Qdrant 派生索引。"""

from __future__ import annotations

from datetime import UTC, datetime
from secrets import token_hex
from time import perf_counter

from taichu.application.contracts.embedding import EmbeddingGateway
from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)
from taichu.application.contracts.vector_index import (
    VectorIndexBackend,
    VectorIndexManifestRepository,
)
from taichu.application.embeddings.models import (
    EmbeddingNormalization,
    EmbeddingPurpose,
    EmbeddingRequest,
)
from taichu.application.retrieval.vector_documents import (
    PROJECTION_STRATEGY_ID,
    KnowledgeVectorDocument,
    knowledge_snapshot_sha256,
    project_confirmed_knowledge_cards,
)
from taichu.application.retrieval.vector_index_models import (
    VectorIndexBuildPlan,
    VectorIndexBuildResult,
    VectorIndexManifest,
    VectorIndexPoint,
    VectorIndexVerification,
)


class KnowledgeVectorIndexService:
    """维护可删除、可重建且不会反向成为事实源的向量索引。"""

    def __init__(
        self,
        *,
        knowledge_repository: StructuredKnowledgeRepository,
        embedding_gateway: EmbeddingGateway,
        vector_index: VectorIndexBackend,
        manifests: VectorIndexManifestRepository,
        active_alias: str,
        document_batch_size: int = 16,
        embedding_input_char_budget: int = 24_000,
    ) -> None:
        if document_batch_size < 1 or document_batch_size > 128:
            raise ValueError("向量文档批大小必须为 1 到 128。")
        if embedding_input_char_budget < 1:
            raise ValueError("Embedding 字符预算必须大于零。")
        self._knowledge_repository = knowledge_repository
        self._embedding_gateway = embedding_gateway
        self._vector_index = vector_index
        self._manifests = manifests
        self._active_alias = active_alias
        self._document_batch_size = document_batch_size
        self._embedding_input_char_budget = embedding_input_char_budget

    async def plan(self) -> VectorIndexBuildPlan:
        cards = await self._knowledge_repository.list_confirmed_cards()
        documents = project_confirmed_knowledge_cards(cards)
        profile = self._embedding_gateway.profile()
        return VectorIndexBuildPlan(
            card_count=len(cards),
            document_count=len(documents),
            knowledge_snapshot_sha256=knowledge_snapshot_sha256(cards),
            embedding_model_id=profile.model_id,
            vector_dimensions=profile.dimensions,
            active_alias=self._active_alias,
        )

    async def rebuild(self, *, dry_run: bool = False) -> VectorIndexBuildResult:
        cards = await self._knowledge_repository.list_confirmed_cards()
        documents = project_confirmed_knowledge_cards(cards)
        if not documents:
            raise KnowledgeVectorIndexBuildError(
                "VECTOR_INDEX_EMPTY",
                "没有可用于构建向量索引的已确认知识卡。",
            )
        profile = self._embedding_gateway.profile()
        snapshot_sha256 = knowledge_snapshot_sha256(cards)
        plan = VectorIndexBuildPlan(
            card_count=len(cards),
            document_count=len(documents),
            knowledge_snapshot_sha256=snapshot_sha256,
            embedding_model_id=profile.model_id,
            vector_dimensions=profile.dimensions,
            active_alias=self._active_alias,
        )
        if dry_run:
            return VectorIndexBuildResult(status="dry_run", plan=plan)

        timer = perf_counter()
        index_id = _new_index_id()
        physical_collection = f"{self._active_alias}_{index_id.removeprefix('knowledge_vectors_')}"
        previous_alias_target = await self._vector_index.get_alias_target(
            self._active_alias
        )
        alias_switched = False
        try:
            await self._vector_index.create_collection(
                physical_collection,
                dimensions=profile.dimensions,
            )
            for batch_number, batch in enumerate(
                _document_batches(
                    documents,
                    max_count=self._document_batch_size,
                    max_characters=self._embedding_input_char_budget,
                ),
                start=1,
            ):
                embedding = await self._embedding_gateway.embed(
                    EmbeddingRequest(
                        texts=[document.content for document in batch],
                        purpose=EmbeddingPurpose.KNOWLEDGE_DOCUMENT,
                        model_role="knowledge_embedding",
                        input_char_budget=self._embedding_input_char_budget,
                        run_id=index_id,
                        invocation_id=f"index_batch_{batch_number}",
                    )
                )
                _validate_embedding_response(
                    embedding_model_id=embedding.model_id,
                    embedding_dimensions=embedding.dimensions,
                    embedding_normalization=embedding.normalization,
                    vector_count=len(embedding.vectors),
                    expected_model_id=profile.model_id,
                    expected_dimensions=profile.dimensions,
                    expected_count=len(batch),
                )
                await self._vector_index.upsert_points(
                    physical_collection,
                    [
                        VectorIndexPoint(
                            point_id=document.point_id,
                            vector=vector,
                            payload=document.qdrant_payload(),
                        )
                        for document, vector in zip(
                            batch, embedding.vectors, strict=True
                        )
                    ],
                )
            state = await self._vector_index.collection_state(physical_collection)
            if state is None or state.point_count != len(documents):
                raise KnowledgeVectorIndexBuildError(
                    "VECTOR_INDEX_COUNT_MISMATCH",
                    "Qdrant 物理集合条目数与投影文档数不一致。",
                )
            if state.dimensions != profile.dimensions:
                raise KnowledgeVectorIndexBuildError(
                    "VECTOR_INDEX_DIMENSION_MISMATCH",
                    "Qdrant 物理集合维度与 Embedding 模型不一致。",
                )

            manifest = VectorIndexManifest(
                index_id=index_id,
                knowledge_snapshot_sha256=snapshot_sha256,
                embedding_model_id=profile.model_id,
                vector_dimensions=profile.dimensions,
                document_projection_strategy_id=PROJECTION_STRATEGY_ID,
                vector_normalization=profile.normalization,
                card_count=len(cards),
                document_count=len(documents),
                estimated_vector_bytes=(len(documents) * profile.dimensions * 4),
                built_at=_now_iso(),
                build_duration_ms=_elapsed_ms(timer),
                physical_collection_name=physical_collection,
                active_alias=self._active_alias,
            ).finalized()
            await self._vector_index.replace_alias(
                self._active_alias, physical_collection
            )
            alias_switched = True
            await self._manifests.save_active(manifest)
            return VectorIndexBuildResult(
                status="completed",
                plan=plan,
                manifest=manifest,
                previous_alias_target=previous_alias_target,
            )
        except Exception as error:
            rollback_error: Exception | None = None
            if alias_switched:
                try:
                    await self._vector_index.replace_alias(
                        self._active_alias, previous_alias_target
                    )
                except Exception as current_error:  # noqa: BLE001
                    rollback_error = current_error
            try:
                await self._vector_index.delete_collection(physical_collection)
            except Exception:  # noqa: BLE001
                pass
            if rollback_error is not None:
                raise KnowledgeVectorIndexBuildError(
                    "VECTOR_INDEX_ROLLBACK_FAILED",
                    "向量索引构建失败，active alias 回滚也失败。",
                ) from rollback_error
            if isinstance(error, KnowledgeVectorIndexBuildError):
                raise
            raise KnowledgeVectorIndexBuildError(
                "VECTOR_INDEX_BUILD_FAILED", "向量索引构建失败，旧索引保持不变。"
            ) from error

    async def verify(self) -> VectorIndexVerification:
        cards = await self._knowledge_repository.list_confirmed_cards()
        current_snapshot = knowledge_snapshot_sha256(cards)
        issues: list[str] = []
        manifest = await self._manifests.load_active()
        if manifest is None:
            return VectorIndexVerification(
                valid=False,
                current_knowledge_snapshot_sha256=current_snapshot,
                issues=["尚未生成 active 向量索引清单。"],
            )

        profile = self._embedding_gateway.profile()
        alias_target = await self._vector_index.get_alias_target(
            manifest.active_alias
        )
        state = await self._vector_index.collection_state(
            manifest.physical_collection_name
        )
        if manifest.knowledge_snapshot_sha256 != current_snapshot:
            issues.append("MongoDB confirmed 知识快照已变化，向量索引已过期。")
        if manifest.embedding_model_id != profile.model_id:
            issues.append("Embedding 模型标识与 active 清单不一致。")
        if manifest.vector_dimensions != profile.dimensions:
            issues.append("Embedding 模型维度与 active 清单不一致。")
        if manifest.vector_normalization is not profile.normalization:
            issues.append("Embedding 归一化方式与 active 清单不一致。")
        if manifest.document_projection_strategy_id != PROJECTION_STRATEGY_ID:
            issues.append("向量文档投影策略与当前代码不一致。")
        if alias_target != manifest.physical_collection_name:
            issues.append("Qdrant active alias 与清单记录不一致。")
        if state is None:
            issues.append("Qdrant active 物理集合不存在。")
        else:
            if state.point_count != manifest.document_count:
                issues.append("Qdrant 条目数与 active 清单不一致。")
            if state.dimensions != manifest.vector_dimensions:
                issues.append("Qdrant 向量维度与 active 清单不一致。")
        return VectorIndexVerification(
            valid=not issues,
            manifest=manifest,
            current_knowledge_snapshot_sha256=current_snapshot,
            alias_target=alias_target,
            collection_point_count=(state.point_count if state is not None else None),
            issues=issues,
        )


class KnowledgeVectorIndexBuildError(RuntimeError):
    """索引构建或回滚的稳定、可分类错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _document_batches(
    documents: list[KnowledgeVectorDocument],
    *,
    max_count: int,
    max_characters: int,
) -> list[list[KnowledgeVectorDocument]]:
    batches: list[list[KnowledgeVectorDocument]] = []
    current: list[KnowledgeVectorDocument] = []
    current_characters = 0
    for document in documents:
        document_characters = len(document.content)
        if document_characters > max_characters:
            raise KnowledgeVectorIndexBuildError(
                "VECTOR_DOCUMENT_TOO_LARGE",
                "单个向量文档超过 Embedding 字符预算。",
            )
        if current and (
            len(current) >= max_count
            or current_characters + document_characters > max_characters
        ):
            batches.append(current)
            current = []
            current_characters = 0
        current.append(document)
        current_characters += document_characters
    if current:
        batches.append(current)
    return batches


def _validate_embedding_response(
    *,
    embedding_model_id: str,
    embedding_dimensions: int,
    embedding_normalization: EmbeddingNormalization,
    vector_count: int,
    expected_model_id: str,
    expected_dimensions: int,
    expected_count: int,
) -> None:
    if embedding_model_id != expected_model_id:
        raise KnowledgeVectorIndexBuildError(
            "EMBEDDING_MODEL_MISMATCH", "Embedding 响应模型与构建计划不一致。"
        )
    if embedding_dimensions != expected_dimensions:
        raise KnowledgeVectorIndexBuildError(
            "EMBEDDING_DIMENSION_MISMATCH", "Embedding 响应维度与构建计划不一致。"
        )
    if embedding_normalization is not EmbeddingNormalization.L2:
        raise KnowledgeVectorIndexBuildError(
            "EMBEDDING_NORMALIZATION_MISMATCH",
            "Embedding 响应归一化方式与 Cosine 索引要求不一致。",
        )
    if vector_count != expected_count:
        raise KnowledgeVectorIndexBuildError(
            "EMBEDDING_COUNT_MISMATCH", "Embedding 响应数量与文档批次不一致。"
        )


def _new_index_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"knowledge_vectors_{stamp}_{token_hex(3)}"


def _elapsed_ms(timer: float) -> int:
    return max(0, round((perf_counter() - timer) * 1000))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
