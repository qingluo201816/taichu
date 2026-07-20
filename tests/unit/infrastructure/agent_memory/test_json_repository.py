"""自动运行记忆原子仓储与可重建索引测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from taichu.application.agent_memory.models import AgentMemoryKind, MemoryWriteCandidate
from taichu.application.services.agent_memory_service import AgentMemoryService
from taichu.infrastructure.agent_memory import (
    JsonAgentMemoryLexicalIndex,
    JsonAgentMemoryRepository,
)


def test_repository_soft_delete_expiry_and_corrupt_index_rebuild(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        repository = JsonAgentMemoryRepository(tmp_path)
        index = JsonAgentMemoryLexicalIndex(tmp_path)
        service = AgentMemoryService(repository=repository, lexical_index=index)
        entry = await service.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind.WORK_NOTE,
                content="第三人称视角检查已经完成。",
                source_refs=["run:source:node"],
                run_ids=["run_source"],
                conversation_id="conversation_store",
                created_request_index=1,
                expires_after_request_index=3,
                expires_at="2026-07-20T00:00:00Z",
            )
        )
        assert await repository.get(entry.memory_id) == entry
        assert "lifecycle" not in entry.model_dump(mode="json")
        assert not list((tmp_path / "derived" / "general_agent_memory").glob("*.tmp"))

        await index.scores([entry], query_text="第三人称视角")
        index_path = tmp_path / "generated" / "agent_memory_indexes" / "lexical_index.json"
        index_path.write_text("{broken", encoding="utf-8")
        scores = await index.scores([entry], query_text="第三人称视角")
        assert scores[entry.memory_id] > 0

        purged = await repository.purge_expired(as_of="2026-07-21T00:00:00Z")
        assert purged == 1
        assert await repository.query(conversation_id="conversation_store") == []
        deleted = await repository.query(
            conversation_id="conversation_store",
            include_deleted=True,
        )
        assert deleted[0].deleted_at == "2026-07-21T00:00:00Z"

    asyncio.run(scenario())
