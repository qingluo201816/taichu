"""内置 Tool 共用的权限和确定性辅助函数。"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel


INTERNAL_READ_CALLERS = frozenset(
    {
        "orchestrator",
        "canon_evidence",
        "narrative_summary",
        "worldbuilding",
        "character",
        "story_architecture",
        "scene_planning",
        "drafting",
        "revision",
        "consistency_reviewer",
        "narrative_reviewer",
        "style_reviewer",
        "test",
    }
)
ORCHESTRATOR_WRITE_CALLERS = frozenset({"orchestrator", "test"})
EXTERNAL_RESEARCH_CALLERS = frozenset({"orchestrator", "external_research", "test"})


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_model_hash(value: BaseModel | dict[str, object]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(text)
