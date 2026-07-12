"""模型目录、遥测与写作流式 API 集成测试。"""

import json
from pathlib import Path
import tempfile
import unittest

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from taichu.application.models.llm_usage import LLMCallRecord
from taichu.application.services.import_service import ImportService
from taichu.config import Settings
from taichu.infrastructure.llm.mock import MVPNoRealLLMChatModel
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class LLMApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_is_safe_and_default_is_deepseek_v4_pro(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_app(
                Settings(
                    project_assets_dir=Path(temporary_directory),
                    rightcode_api_key=SecretStr(""),
                ),
                knowledge_repository=InMemoryKnowledgeRepository(),
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/llm/models")
                unknown = await client.post("/api/llm/models/unknown/probe")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default_model_id"], "deepseek-v4-pro")
        self.assertEqual(len(payload["models"]), 10)
        deepseek = next(
            item for item in payload["models"] if item["id"] == "deepseek-v4-pro"
        )
        claude = next(
            item for item in payload["models"] if item["id"] == "claude-opus-4-6"
        )
        self.assertTrue(deepseek["enabled"])
        self.assertEqual(deepseek["availability"], "unknown")
        self.assertTrue(claude["upstream_verified"])
        serialized = response.text.lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("token", serialized)
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(unknown.json()["error"]["code"], "LLM_MODEL_UNKNOWN")

    async def test_usage_calls_detail_and_summary_do_not_return_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_app(
                Settings(project_assets_dir=Path(temporary_directory)),
                knowledge_repository=InMemoryKnowledgeRepository(),
            )
            await app.state.llm_usage_repository.append(_record())
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                calls = await client.get(
                    "/api/llm/usage/calls?page=1&page_size=20&model_id=deepseek-v4-pro"
                )
                detail = await client.get("/api/llm/usage/calls/call-api-test")
                summary = await client.get("/api/llm/usage/summary")
                trend = await client.get("/api/llm/usage/trend?bucket=day")

        self.assertEqual(calls.json()["total"], 1)
        self.assertEqual(detail.json()["call_id"], "call-api-test")
        self.assertNotIn("prompt", detail.text.lower())
        self.assertEqual(summary.json()["total_calls"], 1)
        self.assertEqual(summary.json()["unavailable_cost_calls"], 1)
        self.assertEqual(trend.status_code, 200)
        self.assertEqual(trend.json()["bucket"], "day")
        self.assertEqual(trend.json()["points"][0]["total_tokens"], 15)

    async def test_writing_stream_emits_deltas_and_persists_same_output(self) -> None:
        output = json.dumps(
            {
                "output_type": "text_candidate",
                "content": {"text": "秦浩轩向山门走去。"},
            },
            ensure_ascii=False,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            assets_root = Path(temporary_directory)
            storage = ProjectAssetStorageBackend(assets_root)
            await ImportService(storage).import_text(
                "第一章 开始\n秦浩轩站在山门前。", source_name="stream.txt"
            )
            app = create_app(
                Settings(project_assets_dir=assets_root),
                llm=MVPNoRealLLMChatModel(response_text=output),
                knowledge_repository=InMemoryKnowledgeRepository(),
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/writing-ai/runs/stream",
                    json={
                        "button_type": "continue",
                        "chapter_id": "chapter_001",
                        "reference_scope": "chapter",
                        "model_id": "deepseek-v4-pro",
                    },
                )
                events = [json.loads(line) for line in response.text.splitlines()]
                completed = next(item for item in events if item["type"] == "run_completed")
                saved = await client.get(
                    f"/api/writing-ai/runs/{completed['run_id']}"
                )

        deltas = "".join(
            item["delta"] for item in events if item["type"] == "text_delta"
        )
        self.assertEqual(deltas, output)
        self.assertEqual(saved.json()["raw_llm_output"], deltas)


def _record() -> LLMCallRecord:
    return LLMCallRecord(
        call_id="call-api-test",
        run_id="run-api-test",
        task_type="writing_continue",
        task_name="续写",
        feature="写作 AI",
        chapter_ids=["chapter_001"],
        model_id="deepseek-v4-pro",
        model_display_name="DeepSeek V4 Pro",
        upstream_model="deepseek-v4-pro",
        wire_protocol="openai_responses",
        status="completed",
        started_at="2026-07-11T00:00:00Z",
        finished_at="2026-07-11T00:00:01Z",
        duration_ms=1000,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
    )
