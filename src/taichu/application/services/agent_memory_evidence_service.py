"""运行记忆来源指纹解析，不把派生记忆当作小说事实源。"""

from __future__ import annotations

from hashlib import sha256
import json

from taichu.application.contracts.intermediate_artifact import (
    IntermediateArtifactRepository,
)
from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.application.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
)
from taichu.application.services.knowledge_service import (
    KnowledgeCardNotFoundError,
    KnowledgeService,
)


class AgentMemoryEvidenceService:
    """按事实源当前内容计算稳定指纹；基础设施不可用时不误判为失效。"""

    def __init__(
        self,
        *,
        chapter_service: ChapterService,
        knowledge_service: KnowledgeService,
        artifact_repository: IntermediateArtifactRepository,
        project_storage: ProjectAssetStorageContract,
    ) -> None:
        self._chapter_service = chapter_service
        self._knowledge_service = knowledge_service
        self._artifact_repository = artifact_repository
        self._project_storage = project_storage

    async def fingerprint(self, reference: str) -> str | None:
        try:
            if reference == "manuscript:manifest":
                manifest = await self._chapter_service.get_manifest()
                return _payload_sha256(manifest.model_dump(mode="json"))
            if reference == "manuscript:outline":
                return _payload_sha256(await self._project_storage.read_outline())
            if reference.startswith("manuscript:"):
                chapter_id = reference.split(":", 2)[1]
                chapter = await self._chapter_service.read_chapter(chapter_id)
                return _text_sha256(chapter.markdown)
            if reference.startswith("knowledge:"):
                card_id = reference.removeprefix("knowledge:")
                card = await self._knowledge_service.get_card(card_id)
                return _payload_sha256(card.model_dump(mode="json"))
            if reference.startswith("artifact:"):
                artifact_id = reference.removeprefix("artifact:")
                artifact = await self._artifact_repository.get(artifact_id)
                if artifact is None:
                    return _missing_sha256(reference)
                return artifact.content_sha256
        except (ChapterNotFoundError, KnowledgeCardNotFoundError):
            return _missing_sha256(reference)
        except Exception:  # noqa: BLE001
            # MongoDB、文件系统等暂时不可用时不能把“无法验证”误判成“来源已改变”。
            return None
        return None


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _missing_sha256(reference: str) -> str:
    return _text_sha256(f"missing:{reference}")
