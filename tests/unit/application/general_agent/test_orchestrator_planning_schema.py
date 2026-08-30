"""高层编排只看到需要由模型提供的能力输入。"""

from pydantic import BaseModel

from taichu.application.general_agent.capability_resolution import (
    CapabilityContract,
    _native_tool_definition,
)
from taichu.application.general_agent.models import GeneralAgentNodeKind
from taichu.application.general_agent.orchestrator import (
    _invalid_literal_artifact_refs,
)


class _SourceRequest(BaseModel):
    auto_collect: bool
    upstream_artifact_refs: list[str]


class _PlanningInput(BaseModel):
    chapter_id: str
    author_grant_id: str
    external_access_grant_id: str
    idempotency_key: str
    source_request: _SourceRequest


def test_planning_schema_hides_runtime_injected_fields() -> None:
    definition = _native_tool_definition(
        CapabilityContract(
            name="write_test",
            kind=GeneralAgentNodeKind.TOOL,
            description="测试规划 Schema",
            input_schema=_PlanningInput,
        )
    )
    function = definition["function"]
    assert isinstance(function, dict)
    parameters = function["parameters"]
    assert isinstance(parameters, dict)
    assert set(parameters["properties"]) == {"chapter_id", "source_request"}
    assert parameters["required"] == ["chapter_id", "source_request"]
    assert parameters["additionalProperties"] is False


def test_literal_upstream_artifact_refs_require_real_artifact_identity() -> None:
    assert _invalid_literal_artifact_refs(
        {
            "source_request": {
                "upstream_artifact_refs": [
                    f"artifact_{'a' * 32}",
                    "story_arch",
                ]
            }
        }
    ) == ("story_arch",)
