"""在作者授权后实际写入正文补丁。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.chapter_service import ChapterService
from taichu.application.tools._manuscript import (
    manuscript_diff,
    normalize_and_apply_patch,
    patch_id,
)
from taichu.application.tools._shared import (
    ORCHESTRATOR_WRITE_CALLERS,
    sha256_text,
)
from taichu.application.tools.contract import (
    ToolAuthorizationPolicy,
    ToolIdempotencyPolicy,
    ToolManifest,
    ToolReconciliationResult,
    ToolReconciliationStatus,
    ToolSideEffect,
)
from taichu.application.tools.models import (
    ApplyManuscriptPatchInput,
    ApplyManuscriptPatchOutput,
)


manifest = ToolManifest(
    name="apply_manuscript_patch",
    description="在作者授权、哈希和幂等校验后真实写入 Markdown 正文。",
    input_schema=ApplyManuscriptPatchInput,
    output_schema=ApplyManuscriptPatchOutput,
    required_capabilities=frozenset({"chapter_service"}),
    exposures=frozenset({"agent_runtime"}),
    side_effect=ToolSideEffect.WRITE,
    allowed_callers=ORCHESTRATOR_WRITE_CALLERS,
    authorization_policy=ToolAuthorizationPolicy.AUTHOR_GRANT,
    idempotency_policy=ToolIdempotencyPolicy.REQUIRED,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = ApplyManuscriptPatchInput.model_validate(input_data)
    service = context.require("chapter_service", ChapterService)
    chapter = await service.read_chapter(tool_input.chapter_id)
    actual_hash = sha256_text(chapter.markdown)
    if actual_hash != tool_input.base_content_sha256:
        raise ValueError("章节正文已变化，禁止静默覆盖。")
    operations, updated = normalize_and_apply_patch(
        chapter.markdown,
        tool_input.operations,
    )
    actual_patch_id = patch_id(chapter.chapter.id, actual_hash, operations)
    if actual_patch_id != tool_input.patch_id:
        raise ValueError("正文补丁与预览记录不一致。")
    updated_hash = sha256_text(updated)
    if updated_hash != tool_input.expected_content_sha256:
        raise ValueError("正文补丁结果哈希与作者预览不一致。")
    saved = await service.save_chapter(tool_input.chapter_id, updated)
    audit_ref = f"manuscript_write:{sha256_text(tool_input.idempotency_key)[:24]}"
    return ApplyManuscriptPatchOutput(
        chapter_id=saved.chapter.id,
        content_sha256=updated_hash,
        word_count=saved.chapter.word_count,
        unified_diff=manuscript_diff(chapter.markdown, updated, saved.chapter.id),
        audit_ref=audit_ref,
        source_refs=[f"manuscript:{saved.chapter.id}"],
    )


async def reconcile(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> ToolReconciliationResult:
    """通过当前 Markdown 哈希判断补丁是否已经真实落盘。"""
    del invocation
    tool_input = ApplyManuscriptPatchInput.model_validate(input_data)
    chapter = await context.require("chapter_service", ChapterService).read_chapter(
        tool_input.chapter_id
    )
    actual_hash = sha256_text(chapter.markdown)
    evidence = {
        "chapter_id": chapter.chapter.id,
        "actual_content_sha256": actual_hash,
        "expected_content_sha256": tool_input.expected_content_sha256,
        "base_content_sha256": tool_input.base_content_sha256,
    }
    if actual_hash == tool_input.expected_content_sha256:
        output = ApplyManuscriptPatchOutput(
            chapter_id=chapter.chapter.id,
            content_sha256=actual_hash,
            word_count=chapter.chapter.word_count,
            unified_diff="",
            audit_ref=(
                f"manuscript_write:{sha256_text(tool_input.idempotency_key)[:24]}"
            ),
            source_refs=[f"manuscript:{chapter.chapter.id}"],
        )
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.SUCCEEDED,
            output=output.model_dump(mode="json"),
            evidence=evidence,
            reason="章节正文哈希与授权后的预期哈希一致。",
        )
    if actual_hash == tool_input.base_content_sha256:
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.NOT_APPLIED,
            evidence=evidence,
            reason="章节正文仍是写入前版本。",
        )
    return ToolReconciliationResult(
        status=ToolReconciliationStatus.UNKNOWN,
        evidence=evidence,
        reason="章节正文既不是写入前版本，也不是授权后的预期版本。",
    )
