"""通用 Agent 节点输入绑定路径协议测试。"""

import pytest
from pydantic import ValidationError

from taichu.application.general_agent.executor import _write_path
from taichu.application.general_agent.models import GeneralAgentInputBinding


def test_binding_normalizes_bracket_array_indexes() -> None:
    binding = GeneralAgentInputBinding(
        source_node_id="read_chapter",
        source_path="output.chunks[0].content",
        target_path="chapter_ids[0]",
    )

    assert binding.source_path == "chunks.0.content"
    assert binding.target_path == "chapter_ids.0"

    payload: dict[str, object] = {"chapter_ids": []}
    _write_path(payload, binding.target_path, "chapter-9")
    assert payload == {"chapter_ids": ["chapter-9"]}


def test_binding_rejects_unsupported_path_syntax() -> None:
    with pytest.raises(ValidationError):
        GeneralAgentInputBinding(
            source_node_id="read_chapter",
            source_path="chunks[*].content",
            target_path="text",
        )
