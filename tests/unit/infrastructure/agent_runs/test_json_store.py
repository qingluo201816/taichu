"""Agent run JSON store tests."""

import json
import tempfile
import unittest
from pathlib import Path

from taichu.domain.models.agent_run import (
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
                {
                    "mention_id": "mention_001_001",
                    "name": "秦阳",
                    "knowledge_type": "character",
                    "description": "秦阳走入太初教山门。",
                    "evidence_excerpts": ["秦阳握着青铜令牌走入太初教山门。"],
                    "reason": "稳定专名角色。",
                    "segment_index": 1,
                }
            ],
            entity_groups=[
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
            ],
            ignored=[
                {
                    "text": "少年们",
                    "reason": "普通人群泛称。",
                    "segment_index": 1,
                }
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

    async def test_legacy_run_json_without_replay_fields_is_still_readable(self) -> None:
        run_id = "extract_run_20260704_153023_b1c2d3"
        root = (
            self.assets_root
            / "derived"
            / "agent_runs"
            / "knowledge_extraction"
        )
        root.mkdir(parents=True)
        (root / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
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

    async def test_invalid_run_id_is_rejected(self) -> None:
        run = AgentRun(
            run_id="bad",
            scope=AgentRunScope(chapter_id="chapter_001"),
            started_at="2026-07-04T15:30:22Z",
        )

        with self.assertRaisesRegex(ValueError, "运行 ID 格式不正确"):
            await self.store.write_run(run)
