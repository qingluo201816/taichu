"""Application service for rebuildable generated projections."""

from datetime import UTC, datetime
from uuid import uuid4

from taichu.application.contracts.indexer import IndexerContract
from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models.indexing import (
    IndexBuildJob,
    IndexBuildJobAction,
    IndexBuildJobStatus,
)


class IndexService:
    """Rebuild generated retrieval projections from source assets."""

    def __init__(
        self,
        storage: ProjectAssetStorageContract,
        indexer: IndexerContract,
    ) -> None:
        self._storage = storage
        self._indexer = indexer

    async def clear_generated(self) -> IndexBuildJob:
        """Clear generated projections without touching source assets."""
        created_at = _now_iso()
        try:
            await self._storage.clear_generated()
        except Exception as error:  # noqa: BLE001 - convert to product job status.
            return _job(
                action=IndexBuildJobAction.CLEAR,
                status=IndexBuildJobStatus.FAILED,
                created_at=created_at,
                message=f"清空派生数据失败：{error}",
            )
        return _job(
            action=IndexBuildJobAction.CLEAR,
            status=IndexBuildJobStatus.COMPLETED,
            created_at=created_at,
            message="派生检索数据已清空",
        )

    async def rebuild_generated_projection(self) -> IndexBuildJob:
        """Clear generated data and rebuild projection from source facts."""
        created_at = _now_iso()
        try:
            await self._storage.clear_generated()
            await self._indexer.rebuild()
        except Exception as error:  # noqa: BLE001 - convert to product job status.
            return _job(
                action=IndexBuildJobAction.REBUILD,
                status=IndexBuildJobStatus.FAILED,
                created_at=created_at,
                message=f"重建派生检索数据失败：{error}",
            )
        return _job(
            action=IndexBuildJobAction.REBUILD,
            status=IndexBuildJobStatus.COMPLETED,
            created_at=created_at,
            message="已从源资产重建派生检索数据",
        )


def _job(
    *,
    action: IndexBuildJobAction,
    status: IndexBuildJobStatus,
    created_at: str,
    message: str,
) -> IndexBuildJob:
    return IndexBuildJob(
        id=f"index_job_{uuid4().hex}",
        action=action,
        status=status,
        created_at=created_at,
        completed_at=_now_iso(),
        message=message,
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
