"""正文初稿生成专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import (
    SubagentManifest,
    SubagentResourceLimits,
)
from taichu.application.subagents.models import DraftingInput, DraftingOutput

manifest = SubagentManifest(
    name="drafting",
    label="正文初稿生成",
    description="生成新写、续写和扩写正文候选。",
    non_responsibilities=("不直接修改 Markdown", "不承担原文保留型修改"),
    input_schema=DraftingInput,
    output_schema=DraftingOutput,
    artifact_types=frozenset({"manuscript_candidate"}),
    model_role="drafting",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {
            "canon_evidence_report",
            "external_research_report",
            "narrative_summary",
            "worldbuilding_proposal",
            "character_proposal",
            "story_architecture",
            "scene_plan",
        }
    ),
    limits=SubagentResourceLimits(max_output_chars=120_000, max_output_tokens=20_000),
)


async def run(
    input_data: BaseModel, invocation: InvocationContext, context: CapabilityContext
) -> BaseModel:
    return await execute(manifest, input_data, invocation, context)
