"""基于 LangGraph 官方 Store 的可恢复能力结果仓储。"""

from __future__ import annotations

import re

from langgraph.store.base import BaseStore, Item, SearchItem

from taichu.application.contracts.general_agent_capability_results import (
    CapabilityResultConflictError,
    CapabilityResultInvalidIdentityError,
    CapabilityResultOwner,
    CapabilityResultOwnerMismatchError,
    CapabilityResultRecord,
    CapabilityResultRecordCorruptError,
    DeleteRunOutcome,
    capability_result_id,
)

_NAMESPACE_PREFIX = ("taichu", "general_agent_capability_results")
_RESULT_ID_PATTERN = re.compile(r"^cr_[a-f0-9]{64}$")
_SEARCH_PAGE_SIZE = 500


class LangGraphGeneralAgentCapabilityResultRepository:
    """用 namespace/key/value 保存确定性能力完成记录，不再维护平行索引。"""

    def __init__(self, store: BaseStore) -> None:
        self.store = store

    async def get_completed(
        self,
        owner: CapabilityResultOwner,
        result_id: str,
    ) -> CapabilityResultRecord | None:
        _validate_result_id(result_id)
        item = await self.store.aget(self._namespace(owner), result_id)
        if item is None:
            return None
        return self._validate_item(item, owner=owner, result_id=result_id)

    async def commit_completed(
        self,
        owner: CapabilityResultOwner,
        record: CapabilityResultRecord,
    ) -> CapabilityResultRecord:
        self._validate_commit(owner, record)
        existing = await self.get_completed(owner, record.result_id)
        if existing is not None:
            if existing.semantic_content_sha256 != record.semantic_content_sha256:
                raise CapabilityResultConflictError()
            return existing
        await self.store.aput(
            self._namespace(owner),
            record.result_id,
            record.model_dump(mode="json"),
        )
        committed = await self.get_completed(owner, record.result_id)
        if committed is None:
            raise CapabilityResultRecordCorruptError(
                "能力结果写入 LangGraph Store 后无法回读。"
            )
        if committed.semantic_content_sha256 != record.semantic_content_sha256:
            raise CapabilityResultConflictError()
        return committed

    async def list_for_run(
        self,
        owner: CapabilityResultOwner,
    ) -> tuple[CapabilityResultRecord, ...]:
        records = [
            self._validate_item(item, owner=owner, result_id=item.key)
            for item in await self._search_all(self._namespace(owner))
        ]
        return tuple(
            sorted(records, key=lambda item: (item.committed_at, item.result_id))
        )

    async def delete_run(
        self,
        owner: CapabilityResultOwner,
    ) -> DeleteRunOutcome:
        records = await self.list_for_run(owner)
        if not records:
            return DeleteRunOutcome.NOT_FOUND
        namespace = self._namespace(owner)
        for record in records:
            await self.store.adelete(namespace, record.result_id)
        return DeleteRunOutcome.DELETED

    async def _search_all(
        self,
        namespace: tuple[str, ...],
    ) -> list[SearchItem]:
        result: list[SearchItem] = []
        offset = 0
        while True:
            page = await self.store.asearch(
                namespace,
                limit=_SEARCH_PAGE_SIZE,
                offset=offset,
            )
            result.extend(page)
            if len(page) < _SEARCH_PAGE_SIZE:
                return result
            offset += len(page)

    @staticmethod
    def _namespace(owner: CapabilityResultOwner) -> tuple[str, ...]:
        return (*_NAMESPACE_PREFIX, owner.conversation_id, owner.run_id)

    @staticmethod
    def _validate_commit(
        owner: CapabilityResultOwner,
        record: CapabilityResultRecord,
    ) -> None:
        if record.owner != owner or record.identity.owner != owner:
            raise CapabilityResultOwnerMismatchError()
        if record.result_id != capability_result_id(record.identity):
            raise CapabilityResultInvalidIdentityError(
                "能力结果标识与身份载荷不一致。"
            )

    @staticmethod
    def _validate_item(
        item: Item | SearchItem,
        *,
        owner: CapabilityResultOwner,
        result_id: str,
    ) -> CapabilityResultRecord:
        try:
            record = CapabilityResultRecord.model_validate(item.value)
        except ValueError as error:
            raise CapabilityResultRecordCorruptError(
                f"LangGraph Store 中的能力结果“{result_id}”校验失败。"
            ) from error
        if item.key != result_id or record.result_id != result_id:
            raise CapabilityResultRecordCorruptError(
                "LangGraph Store key 与能力结果标识不一致。"
            )
        if record.owner != owner or record.identity.owner != owner:
            raise CapabilityResultOwnerMismatchError()
        return record


def _validate_result_id(result_id: str) -> None:
    if _RESULT_ID_PATTERN.fullmatch(result_id) is None:
        raise CapabilityResultInvalidIdentityError("能力结果标识格式不正确。")
