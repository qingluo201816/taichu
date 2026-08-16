"""Agent run JSON store tests."""

import json
import tempfile
import unittest
from pathlib import Path

from taichu.application.agents.models.agent_run import (
    AgentBatchChapterProgress,
    AgentEntityGroup,
    AgentIgnoredExtraction,
    AgentRawMention,
    AgentRun,
    AgentRunScope,
    AgentRunStatus,
)
from taichu.infrastructure.agent_runs import JsonAgentRunStore


class JsonAgentRunStoreTest(unittest.IsolatedAsyncioTestCase):
    """Verify derived run files are written and listed."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.store = JsonAgentRunStore(self.assets_root)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_write_get_and_list_run(self) -> None:
        run = AgentRun(
            run_id="extract_run_20260704_153022_a1b2c3",
            status=AgentRunStatus.COMPLETED,
            scope=AgentRunScope(
                chapter_id="chapter_001",
                chapter_title="第一章",
                content_hash="sha256",
            ),
            started_at="2026-07-04T15:30:22Z",
            finished_at="2026-07-04T15:30:23Z",
            raw_mentions=[
                AgentRawMention.model_validate(
                    {
                        "mention_id": "mention_001_001",
                        "name": "秦阳",
                        "knowledge_type": "character",
                        "description": "秦阳走入太初教山门。",
                        "evidence_excerpts": ["秦阳握着青铜令牌走入太初教山门。"],
                        "reason": "稳定专名角色。",
                        "segment_index": 1,
                    }
                )
            ],
            entity_groups=[
                AgentEntityGroup.model_validate(
                    {
                        "entity_group_id": "entity_group_001",
                        "canonical_name": "秦阳",
                        "knowledge_type": "character",
                        "raw_names": ["秦阳"],
                        "mention_count": 1,
                        "evidence_excerpts": ["秦阳握着青铜令牌走入太初教山门。"],
                        "quality_decision": "accepted",
                        "quality_reason": "稳定专名角色。",
                    }
                )
            ],
            ignored=[
                AgentIgnoredExtraction.model_validate(
                    {
                        "text": "少年们",
                        "reason": "普通人群泛称。",
                        "segment_index": 1,
                    }
                )
            ],
        )

        await self.store.write_run(run)
        loaded = await self.store.get_run(run.run_id)
        runs, total = await self.store.list_runs(status="completed")
        path = (
            self.assets_root
            / "derived"
            / "agent_runs"
            / "knowledge_extraction"
            / f"{run.run_id}.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded, run)
        self.assertEqual(data["raw_mentions"][0]["name"], "秦阳")
        self.assertEqual(data["entity_groups"][0]["canonical_name"], "秦阳")
        self.assertEqual(data["ignored"][0]["text"], "少年们")
        self.assertEqual(total, 1)
        self.assertEqual([item.run_id for item in runs], [run.run_id])
        self.assertTrue(path.exists())

    async def test_legacy_run_json_without_replay_fields_is_still_readable(
        self,
    ) -> None:
        run_id = "extract_run_20260704_153023_b1c2d3"
        root = self.assets_root / "derived" / "agent_runs" / "knowledge_extraction"
        root.mkdir(parents=True)
        (root / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "model_name": "legacy-display-name",
                    "status": "completed",
                    "scope": {
                        "chapter_id": "chapter_001",
                        "chapter_title": "第一章",
                    },
                    "started_at": "2026-07-04T15:30:22Z",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        loaded = await self.store.get_run(run_id)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.raw_mentions, [])
        self.assertEqual(loaded.entity_groups, [])
        self.assertEqual(loaded.ignored, [])
        self.assertFalse(loaded.generation_model_identity.known)
        self.assertEqual(
            loaded.generation_model_identity.model_id,
            "legacy-display-name",
        )
        self.assertEqual(
            loaded.generation_model_identity.unknown_reason,
            "旧运行记录未保存真实模型身份。",
        )

    async def test_invalid_run_id_is_rejected(self) -> None:
        run = AgentRun(
            run_id="bad",
            scope=AgentRunScope(chapter_id="chapter_001"),
            started_at="2026-07-04T15:30:22Z",
        )

        with self.assertRaisesRegex(ValueError, "运行 ID 格式不正确"):
            await self.store.write_run(run)

    async def test_deleted_run_cannot_be_recreated_by_late_write(self) -> None:
        run = AgentRun(
            run_id="extract_run_20260704_153024_c1d2e3",
            status=AgentRunStatus.RUNNING,
            scope=AgentRunScope(chapter_id="chapter_001"),
            started_at="2026-07-04T15:30:22Z",
        )
        await self.store.write_run(run)

        self.assertTrue(await self.store.delete_run(run.run_id))
        await self.store.write_run(
            run.model_copy(update={"status": AgentRunStatus.COMPLETED})
        )

        self.assertIsNone(await self.store.get_run(run.run_id))

    async def test_legacy_completed_batch_with_failed_chapter_is_read_as_failed(
        self,
    ) -> None:
        run = AgentRun(
            run_id="extract_run_20260704_153025_d4e5f6",
            status=AgentRunStatus.COMPLETED,
            scope=AgentRunScope(
                scope_type="chapter_batch",
                chapter_id="chapter_071",
                chapter_ids=["chapter_071"],
            ),
            started_at="2026-07-04T15:30:22Z",
            batch_chapter_progress=[
                AgentBatchChapterProgress(
                    chapter_id="chapter_071",
                    chapter_title="第71章",
                    status="failed",
                    error="当前密钥无权调用该模型，请检查本机密钥权限。",
                )
            ],
            total_chapter_count=1,
            failed_chapter_count=1,
        )
        await self.store.write_run(run)

        loaded = await self.store.get_run(run.run_id)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.status, AgentRunStatus.FAILED)
        self.assertIn("第71章：当前密钥无权调用该模型", loaded.errors[0])
