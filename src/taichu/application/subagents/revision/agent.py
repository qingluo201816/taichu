"""正文修改专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import (
    SubagentManifest,
    SubagentResourceLimits,
)
from taichu.application.subagents.models import RevisionInput, RevisionOutput

manifest = SubagentManifest(
    name="revision",
    label="正文修改",
    description="在保留原意和事实约束下改写、缩写、润色或调整正文。",
    non_responsibilities=("不直接修改 Markdown", "不承担无原文的新写任务"),
    input_schema=RevisionInput,
    output_schema=RevisionOutput,
    artifact_types=frozenset({"revision_candidate"}),
    model_role="revision",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {
            "canon_evidence_report",
            "story_architecture",
            "scene_plan",
            "manuscript_candidate",
            "consistency_review",
            "narrative_review",
            "style_review",
        }
    ),
    limits=SubagentResourceLimits(max_output_chars=160_000, max_output_tokens=24_000),
)


async def run(
    runtime_manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    return await execute(runtime_manifest, input_data, invocation, context)
