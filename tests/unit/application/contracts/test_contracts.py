"""Application contract Protocol tests."""

import unittest

from pydantic import ValidationError

from taichu.application.contracts import (
    LLMCost,
    LLMGatewayContract,
    LLMModelIdentity,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
    StorageContract,
)
from taichu.application.contracts.agent_run_repository import AgentRunRepository


class DummyStorage:
    """Storage contract stub."""

    async def get(
        self,
        collection: str,
        key: str,
    ) -> dict[str, object] | None:
        return {"collection": collection, "key": key}

    async def list(self, collection: str) -> list[dict[str, object]]:
        return [{"collection": collection}]

    async def put(
        self,
        collection: str,
        key: str,
        data: dict[str, object],
    ) -> None:
        return None

    async def delete(self, collection: str, key: str) -> bool:
        return True


class DummyLLM:
    """LLM contract stub."""

    @property
    def model_identity(self) -> LLMModelIdentity:
        return LLMModelIdentity(
            provider="test",
            model_id="dummy",
            family="dummy",
            endpoint_kind="test",
            known=True,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=str(request),
            model_id="dummy",
            upstream_model="dummy",
            usage=LLMUsage(),
            cost=LLMCost(),
        )

    async def _stream(self):
        yield LLMStreamEvent(event_type="completed")

    def stream(self, request: LLMRequest):
        return self._stream()

    def list_models(self) -> list[LLMModelProfile]:
        return [
            LLMModelProfile(
                id="dummy",
                display_name="测试模型",
                provider="rightcode",
                upstream_model="dummy",
                wire_protocol="openai_responses",
                base_url_key="RIGHTCODE_RESPONSES_BASE_URL",
                enabled=True,
                is_default=True,
                supports_streaming=True,
            )
        ]


class DummyAgentRunRepository:
    """Agent run repository contract stub."""

    async def write_run(self, run):
        return run

    async def get_run(self, run_id: str):
        return None

    async def delete_run(self, run_id: str) -> bool:
        return False

    async def list_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ):
        return [], 0

    async def find_run_for_candidate(self, candidate_id: str):
        return None


class ApplicationContractTest(unittest.IsolatedAsyncioTestCase):
    """Verify Phase 0 application contract entry points exist."""

    async def test_protocols_accept_minimal_stubs(self) -> None:
        storage = DummyStorage()
        llm = DummyLLM()
        run_repository = DummyAgentRunRepository()

        self.assertIsInstance(storage, StorageContract)
        self.assertIsInstance(llm, LLMGatewayContract)
        self.assertIsInstance(run_repository, AgentRunRepository)

    async def test_model_identity_requires_explicit_known_or_unknown_state(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValidationError, "供应商和模型标识"):
            LLMModelIdentity(known=True)
        with self.assertRaisesRegex(ValidationError, "必须说明原因"):
            LLMModelIdentity()

        identity = LLMModelIdentity.unknown("测试无法识别模型。")
        with self.assertRaises(ValidationError):
            identity.model_id = "changed"
