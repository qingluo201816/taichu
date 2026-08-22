"""高层编排只看到需要由模型提供的能力输入。"""

from taichu.application.general_agent.orchestrator import (
    _invalid_literal_artifact_refs,
    _planning_schema,
)


def test_planning_schema_hides_runtime_injected_fields() -> None:
    schema = {
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string"},
            "author_grant_id": {"type": "string"},
            "external_access_grant_id": {"type": "string"},
            "idempotency_key": {"type": "string"},
            "source_request": {
                "type": "object",
                "properties": {
                    "auto_collect": {"type": "boolean"},
                    "upstream_artifact_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["auto_collect", "upstream_artifact_refs"],
            },
        },
        "required": [
            "chapter_id",
            "author_grant_id",
            "external_access_grant_id",
            "idempotency_key",
            "source_request",
        ],
    }

    projected = _planning_schema(schema)

    assert projected["properties"] == {
        "chapter_id": {"type": "string"},
        "source_request": {
            "type": "object",
            "properties": {
                "auto_collect": {"type": "boolean"},
                "upstream_artifact_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["auto_collect", "upstream_artifact_refs"],
        },
    }
    assert projected["required"] == ["chapter_id", "source_request"]


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
