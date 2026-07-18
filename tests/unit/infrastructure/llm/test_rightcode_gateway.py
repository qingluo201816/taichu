"""Right Code 统一 Responses 与 Messages 网关测试。"""

import asyncio
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from pydantic import SecretStr

from taichu.application.contracts.llm import LLMMessage, LLMRequest
from taichu.application.models.llm_usage import LLMUsageQuery
from taichu.config import Settings
from taichu.infrastructure.llm.catalog import (
    LLMModelCatalog,
    LLMModelSelectionError,
)
from taichu.infrastructure.llm.rightcode import (
    RightCodeGatewayError,
    RightCodeLLMGateway,
)
from taichu.infrastructure.llm_usage import JsonlLLMUsageRepository


class RightCodeGatewayTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self.temporary_directory.name)

    async def asyncTearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_catalog_has_ten_unique_models_and_one_default(self) -> None:
        catalog = LLMModelCatalog(_settings(self.assets_root))
        profiles = catalog.list_models()
        self.assertEqual(len(profiles), 10)
        self.assertEqual(len({item.id for item in profiles}), 10)
        self.assertEqual(
            [item.id for item in profiles if item.is_default],
            ["deepseek-v4-pro"],
        )
        self.assertEqual(
            catalog.resolve("deepseek-v4-pro").upstream_model,
            "deepseek-v4-pro",
        )
        self.assertEqual(
            catalog.resolve("claude-opus-4-6").wire_protocol,
            "anthropic_messages",
        )
        self.assertEqual(
            catalog.resolve("deepseek-v4-pro").wire_protocol,
            "anthropic_messages",
        )
        self.assertTrue(all(item.upstream_verified for item in profiles))

    def test_unknown_model_is_rejected_with_stable_chinese_error(self) -> None:
        catalog = LLMModelCatalog(_settings(self.assets_root))
        with self.assertRaises(LLMModelSelectionError) as context:
            catalog.resolve("unknown")
        self.assertEqual(context.exception.code, "LLM_MODEL_UNKNOWN")
        self.assertIn("模型不存在", context.exception.message)

    async def test_model_selection_changes_upstream_and_is_concurrency_safe(
        self,
    ) -> None:
        requested_models: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            requested_models.append(payload["model"])
            await asyncio.sleep(0)
            if request.url.path.endswith("/v1/messages"):
                return httpx.Response(
                    200,
                    json={
                        "id": "claude-request",
                        "content": [{"type": "text", "text": payload["model"]}],
                        "usage": {"input_tokens": 2, "output_tokens": 1},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "id": f"request-{len(requested_models)}",
                    "output_text": payload["model"],
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                },
            )

        gateway, client, _ = self._gateway(httpx.MockTransport(handler))
        try:
            responses = await asyncio.gather(
                gateway.complete(_request("gpt-5-6-luna")),
                gateway.complete(_request("claude-opus-4-6")),
            )
        finally:
            await client.aclose()
        self.assertEqual(set(requested_models), {"gpt-5.6-luna", "claude-opus-4-6"})
        self.assertEqual(
            {item.upstream_model for item in responses}, set(requested_models)
        )

    async def test_responses_usage_and_actual_cost_are_normalized(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "provider-request",
                    "output": [{"content": [{"type": "output_text", "text": "完成"}]}],
                    "usage": {
                        "input_tokens": 12,
                        "input_tokens_details": {"cached_tokens": 3},
                        "output_tokens": 5,
                        "output_tokens_details": {"reasoning_tokens": 2},
                        "total_tokens": 17,
                    },
                    "billing": {"amount": "0.1234", "currency": "CNY"},
                },
            )

        gateway, client, repository = self._gateway(httpx.MockTransport(handler))
        try:
            response = await gateway.complete(_request("gpt-5-6-luna"))
        finally:
            await client.aclose()
        self.assertEqual(response.text, "完成")
        self.assertEqual(response.usage.cached_input_tokens, 3)
        self.assertEqual(response.usage.reasoning_tokens, 2)
        self.assertEqual(response.cost.amount, Decimal("0.1234"))
        self.assertEqual(response.cost.kind, "actual")
        record = await repository.get(response.call_id or "")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.provider_request_id, "provider-request")

    async def test_responses_sse_stream_is_normalized(self) -> None:
        sse = "\n".join(
            [
                "event: response.output_text.delta",
                'data: {"type":"response.output_text.delta","delta":"秦浩"}',
                "",
                "event: response.output_text.delta",
                'data: {"type":"response.output_text.delta","delta":"轩"}',
                "",
                "event: response.completed",
                (
                    'data: {"type":"response.completed","response":'
                    '{"id":"stream-request","output_text":"秦浩轩",'
                    '"usage":{"input_tokens":3,"output_tokens":2,'
                    '"total_tokens":5}}}'
                ),
                "",
            ]
        )

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse.encode(),
            )

        gateway, client, _ = self._gateway(httpx.MockTransport(handler))
        try:
            events = [event async for event in gateway.stream(_request("gpt-5-6-sol"))]
        finally:
            await client.aclose()
        self.assertEqual(
            "".join(item.delta for item in events if item.event_type == "text_delta"),
            "秦浩轩",
        )
        completed = next(item for item in events if item.event_type == "completed")
        assert completed.response is not None
        self.assertEqual(completed.response.usage.total_tokens, 5)

    async def test_claude_messages_response_is_normalized(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["payload"] = json.loads(request.content)
            captured["has_anthropic_version"] = "anthropic-version" in request.headers
            return httpx.Response(
                200,
                json={
                    "id": "message-request",
                    "content": [{"type": "text", "text": "完成"}],
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": 7,
                        "cache_read_input_tokens": 3,
                        "output_tokens": 2,
                    },
                },
            )

        gateway, client, _ = self._gateway(httpx.MockTransport(handler))
        try:
            response = await gateway.complete(_request("claude-opus-4-6"))
        finally:
            await client.aclose()
        payload = captured["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(captured["path"], "/claude-sale/v1/messages")
        self.assertTrue(captured["has_anthropic_version"])
        self.assertEqual(payload["system"], "系统约束")
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertEqual(response.text, "完成")
        self.assertEqual(response.usage.cached_input_tokens, 3)
        self.assertEqual(response.usage.total_tokens, 9)
        self.assertEqual(response.finish_reason, "end_turn")

    async def test_claude_messages_sse_stream_is_normalized(self) -> None:
        sse = "\n".join(
            [
                "event: message_start",
                'data: {"type":"message_start","message":{"id":"msg-stream","usage":{"input_tokens":4}}}',
                "",
                "event: content_block_delta",
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"秦浩"}}',
                "",
                "event: content_block_delta",
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"轩"}}',
                "",
                "event: message_delta",
                'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}',
                "",
                "event: message_stop",
                'data: {"type":"message_stop"}',
                "",
            ]
        )

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse.encode(),
            )

        gateway, client, _ = self._gateway(httpx.MockTransport(handler))
        try:
            events = [
                event async for event in gateway.stream(_request("claude-sonnet-4-6"))
            ]
        finally:
            await client.aclose()
        self.assertEqual(
            "".join(item.delta for item in events if item.event_type == "text_delta"),
            "秦浩轩",
        )
        completed = next(item for item in events if item.event_type == "completed")
        assert completed.response is not None
        self.assertEqual(completed.response.provider_request_id, "msg-stream")
        self.assertEqual(completed.response.usage.total_tokens, 6)

    async def test_json_mode_removes_markdown_fence_after_complete_response(
        self,
    ) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "json-message",
                    "content": [{"type": "text", "text": '```json\n{"ok":true}\n```'}],
                    "usage": {"input_tokens": 4, "output_tokens": 4},
                },
            )

        gateway, client, _ = self._gateway(httpx.MockTransport(handler))
        try:
            response = await gateway.complete(
                replace(_request("claude-opus-4-6"), response_mode="json")
            )
        finally:
            await client.aclose()
        self.assertEqual(response.text, '{"ok":true}')

    async def test_deepseek_uses_rightcode_anthropic_channel(self) -> None:
        captured_path = ""

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_path
            captured_path = request.url.path
            return httpx.Response(
                200,
                json={
                    "id": "deepseek-message",
                    "content": [{"type": "text", "text": "可用"}],
                    "usage": {"input_tokens": 3, "output_tokens": 1},
                },
            )

        gateway, client, _ = self._gateway(httpx.MockTransport(handler))
        try:
            response = await gateway.complete(_request("deepseek-v4-pro"))
        finally:
            await client.aclose()
        self.assertEqual(captured_path, "/deepseek/anthropic/v1/messages")
        self.assertEqual(response.text, "可用")

    async def test_deepseek_probe_reserves_reasoning_output_budget(self) -> None:
        captured_max_tokens = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_max_tokens
            payload = json.loads(request.content)
            captured_max_tokens = payload["max_tokens"]
            return httpx.Response(
                200,
                json={
                    "id": "deepseek-probe",
                    "content": [{"type": "text", "text": "可用"}],
                    "usage": {"input_tokens": 3, "output_tokens": 1},
                },
            )

        gateway, client, _ = self._gateway(httpx.MockTransport(handler))
        try:
            state = await gateway.probe_model("deepseek-v4-pro")
        finally:
            await client.aclose()
        self.assertEqual(captured_max_tokens, 1024)
        self.assertEqual(state.availability, "available")

    async def test_empty_response_is_retried_and_recovers(self) -> None:
        request_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            text = "" if request_count == 1 else "重试后可用"
            return httpx.Response(
                200,
                json={
                    "id": f"deepseek-message-{request_count}",
                    "content": [{"type": "text", "text": text}],
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                },
            )

        gateway, client, repository = self._gateway(
            httpx.MockTransport(handler),
            max_retries=1,
        )
        try:
            response = await gateway.complete(_request("deepseek-v4-pro"))
        finally:
            await client.aclose()
        self.assertEqual(response.text, "重试后可用")
        self.assertEqual(request_count, 2)
        records = await repository.list_calls(LLMUsageQuery())
        self.assertEqual(records.total, 1)
        self.assertEqual(records.items[0].status, "completed")

    async def test_repeated_empty_response_uses_retry_limit(self) -> None:
        request_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(
                200,
                json={
                    "id": f"deepseek-message-{request_count}",
                    "content": [],
                    "usage": {"input_tokens": 3, "output_tokens": 0},
                },
            )

        gateway, client, repository = self._gateway(
            httpx.MockTransport(handler),
            max_retries=1,
        )
        try:
            with self.assertRaises(RightCodeGatewayError) as context:
                await gateway.complete(_request("deepseek-v4-pro"))
        finally:
            await client.aclose()
        self.assertEqual(context.exception.code, "LLM_EMPTY_RESPONSE")
        self.assertEqual(request_count, 2)
        records = await repository.list_calls(LLMUsageQuery())
        self.assertEqual(records.total, 1)
        self.assertEqual(records.items[0].status, "failed")
        self.assertEqual(records.items[0].error_code, "LLM_EMPTY_RESPONSE")

    async def test_price_missing_is_unavailable_and_configured_price_is_estimated(
        self,
    ) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "output_text": "完成",
                    "usage": {"input_tokens": 1_000_000, "output_tokens": 2},
                },
            )

        gateway, client, _ = self._gateway(httpx.MockTransport(handler))
        try:
            unavailable = await gateway.complete(_request("gpt-5-6-luna"))
        finally:
            await client.aclose()
        self.assertIsNone(unavailable.cost.amount)
        self.assertEqual(unavailable.cost.kind, "unavailable")

        prices = json.dumps({"gpt-5-6-luna": {"input": "2", "output": "3"}})
        gateway, client, _ = self._gateway(
            httpx.MockTransport(handler), prices_json=prices
        )
        try:
            estimated = await gateway.complete(_request("gpt-5-6-luna"))
        finally:
            await client.aclose()
        self.assertEqual(estimated.cost.kind, "estimated")
        self.assertEqual(estimated.cost.amount, Decimal("2.000006"))

    async def test_failure_record_and_error_do_not_contain_secret_or_upstream_body(
        self,
    ) -> None:
        secret = "test-rightcode-key"

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                text=f"上游调试信息包含 {secret} 和内部堆栈",
            )

        gateway, client, repository = self._gateway(
            httpx.MockTransport(handler), key=secret
        )
        try:
            with self.assertRaises(RightCodeGatewayError) as context:
                await gateway.complete(_request("claude-opus-4-6"))
        finally:
            await client.aclose()
        self.assertNotIn(secret, str(context.exception))
        records = await repository.list_calls(LLMUsageQuery())
        self.assertEqual(records.total, 1)
        serialized = records.items[0].model_dump_json()
        self.assertNotIn(secret, serialized)
        self.assertNotIn("内部堆栈", serialized)

    def _gateway(
        self,
        transport: httpx.AsyncBaseTransport,
        *,
        prices_json: str = "{}",
        key: str = "test-rightcode-key",
        max_retries: int = 0,
    ) -> tuple[RightCodeLLMGateway, httpx.AsyncClient, JsonlLLMUsageRepository]:
        settings = _settings(
            self.assets_root,
            key=key,
            prices_json=prices_json,
            max_retries=max_retries,
        )
        repository = JsonlLLMUsageRepository(self.assets_root)
        client = httpx.AsyncClient(transport=transport)
        return (
            RightCodeLLMGateway(
                settings,
                LLMModelCatalog(settings),
                repository,
                client=client,
            ),
            client,
            repository,
        )


def _settings(
    assets_root: Path,
    *,
    key: str = "test-rightcode-key",
    prices_json: str = "{}",
    max_retries: int = 0,
) -> Settings:
    return Settings(
        project_assets_dir=assets_root,
        rightcode_api_key=SecretStr(key),
        rightcode_model_prices_json=prices_json,
        rightcode_max_retries=max_retries,
    )


def _request(model_id: str) -> LLMRequest:
    return LLMRequest(
        model_id=model_id,
        messages=(
            LLMMessage(role="system", content="系统约束"),
            LLMMessage(role="user", content="用户输入"),
        ),
        task_type="test",
        task_name="网关测试",
        response_mode="text",
    )
