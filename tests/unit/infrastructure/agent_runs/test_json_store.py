"""Agent run JSON store tests."""

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
        )

        await self.store.write_run(run)
        loaded = await self.store.get_run(run.run_id)
        runs, total = await self.store.list_runs(status="completed")

        self.assertEqual(loaded, run)
        self.assertEqual(total, 1)
        self.assertEqual([item.run_id for item in runs], [run.run_id])
        self.assertTrue(
            (
                self.assets_root
                / "derived"
                / "agent_runs"
                / "knowledge_extraction"
                / f"{run.run_id}.json"
            ).exists()
        )

    async def test_invalid_run_id_is_rejected(self) -> None:
        run = AgentRun(
            run_id="bad",
            scope=AgentRunScope(chapter_id="chapter_001"),
            started_at="2026-07-04T15:30:22Z",
        )

        with self.assertRaisesRegex(ValueError, "运行 ID 格式不正确"):
            await self.store.write_run(run)
