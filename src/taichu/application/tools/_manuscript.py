"""正文 Tool 共用的确定性补丁逻辑。"""

from __future__ import annotations

from difflib import unified_diff
import json

from taichu.application.tools._shared import sha256_text
from taichu.application.tools.models import ManuscriptPatchOperation


def normalize_and_apply_patch(
    content: str,
    operations: list[ManuscriptPatchOperation],
) -> tuple[list[ManuscriptPatchOperation], str]:
    """校验不重叠字符区间并产生确定性新正文。"""
    spans = sorted(
        [item for item in operations if item.operation == "replace_span"],
        key=lambda item: int(item.start_char or 0),
    )
    previous_end = 0
    for index, operation in enumerate(spans):
        start = int(operation.start_char or 0)
        end = int(operation.end_char or 0)
        if end > len(content):
            raise ManuscriptPatchConflictError("正文补丁位置超出当前章节范围。")
        if index and start < previous_end:
            raise ManuscriptPatchConflictError("正文补丁包含重叠替换区间。")
        previous_end = end

    updated = content
    for operation in reversed(spans):
        start = int(operation.start_char or 0)
        end = int(operation.end_char or 0)
        updated = updated[:start] + operation.text + updated[end:]

    prepends = [item.text for item in operations if item.operation == "prepend"]
    appends = [item.text for item in operations if item.operation == "append"]
    updated = "".join(prepends) + updated + "".join(appends)
    normalized = [*spans]
    normalized.extend(item for item in operations if item.operation == "prepend")
    normalized.extend(item for item in operations if item.operation == "append")
    return normalized, updated


def patch_id(
    chapter_id: str,
    base_content_sha256: str,
    operations: list[ManuscriptPatchOperation],
) -> str:
    payload = {
        "chapter_id": chapter_id,
        "base_content_sha256": base_content_sha256,
        "operations": [item.model_dump(mode="json") for item in operations],
    }
    value = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return f"patch_{sha256_text(value)}"


def manuscript_diff(old: str, new: str, chapter_id: str) -> str:
    return "".join(
        unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"{chapter_id}:before",
            tofile=f"{chapter_id}:after",
        )
    )


class ManuscriptPatchConflictError(ValueError):
    """正文内容哈希或补丁位置已失效。"""
