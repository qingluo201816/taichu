"""隔离资源采集必须使用稳定业务身份，而不是物理卷目录路径。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from taichu.infrastructure.evaluations.general_agent_benchmark.resource_capture import (
    capture_case_resource_state,
)


class _EmptyKnowledgeRepository:
    async def list_confirmed_cards(self, type=None):  # type: ignore[no-untyped-def]
        del type
        return []


def test_nested_chapter_path_and_structure_items_use_logical_refs(
    tmp_path: Path,
) -> None:
    manuscript_root = tmp_path / "source" / "manuscripts"
    chapter_root = manuscript_root / "chapters" / "volume_fixture"
    chapter_root.mkdir(parents=True)
    (chapter_root / "chapter_001.md").write_bytes(
        "第一章\r\n正文\r\n".encode()
    )
    (manuscript_root / "manifest.json").write_text("{}\n", encoding="utf-8")
    (manuscript_root / "outline.json").write_text(
        json.dumps(
            {
                "volumes": [
                    {
                        "volume_id": "volume_fixture",
                        "name": "评测卷",
                        "chapters": [
                            {
                                "chapter_id": "chapter_001",
                                "display_title": "第一章",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    resources = asyncio.run(
        capture_case_resource_state(
            workspace=tmp_path,
            knowledge_repository=_EmptyKnowledgeRepository(),  # type: ignore[arg-type]
        )
    )
    refs = {item.resource_ref for item in resources}

    assert "manuscript:chapter_001" in refs
    assert "structure:volume:volume_fixture" in refs
    assert "structure:chapter:chapter_001" in refs
    assert not any("volume_fixture/chapter_001.md" in item for item in refs)
    chapter = next(
        item
        for item in resources
        if item.resource_ref == "manuscript:chapter_001"
    )
    assert chapter.content_sha256 == hashlib.sha256(
        "第一章\n正文\n".encode()
    ).hexdigest()
