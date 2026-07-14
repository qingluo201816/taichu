"""无副作用地预览结构化正文补丁。"""

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
from taichu.application.tools.contract import ToolManifest, ToolSideEffect
from taichu.application.tools.models import (
    PreviewManuscriptPatchInput,
    PreviewManuscriptPatchOutput,
)


manifest = ToolManifest(
    name="preview_manuscript_patch",
    description="校验正文基础哈希并生成无副作用差异预览。",
    input_schema=PreviewManuscriptPatchInput,
    output_schema=PreviewManuscriptPatchOutput,
    required_capabilities=frozenset({"chapter_service"}),
    exposures=frozenset({"agent_runtime"}),
    side_effect=ToolSideEffect.PREVIEW,
    allowed_callers=ORCHESTRATOR_WRITE_CALLERS,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = PreviewManuscriptPatchInput.model_validate(input_data)
    chapter = await context.require("chapter_service", ChapterService).read_chapter(
        tool_input.chapter_id
    )
    actual_hash = sha256_text(chapter.markdown)
    if actual_hash != tool_input.base_content_sha256:
        raise ValueError("章节正文已变化，请刷新后重新生成补丁。")
    operations, updated = normalize_and_apply_patch(
        chapter.markdown,
        tool_input.operations,
    )
    return PreviewManuscriptPatchOutput(
        patch_id=patch_id(chapter.chapter.id, actual_hash, operations),
        chapter_id=chapter.chapter.id,
        base_content_sha256=actual_hash,
        expected_content_sha256=sha256_text(updated),
        normalized_operations=operations,
        unified_diff=manuscript_diff(
            chapter.markdown,
            updated,
            chapter.chapter.id,
        ),
        old_char_count=len(chapter.markdown),
        new_char_count=len(updated),
        source_refs=[f"manuscript:{chapter.chapter.id}"],
    )
