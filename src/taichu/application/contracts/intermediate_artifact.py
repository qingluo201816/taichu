"""专业子 Agent 中间产物仓储契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.artifacts.models import IntermediateArtifactRecord


@runtime_checkable
class IntermediateArtifactRepository(Protocol):
    async def save(self, record: IntermediateArtifactRecord) -> None: ...

    async def get(self, artifact_id: str) -> IntermediateArtifactRecord | None: ...
