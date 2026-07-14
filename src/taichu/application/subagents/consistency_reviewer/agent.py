"""一致性审查专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import (
    ConsistencyReviewInput,
    ConsistencyReviewOutput,
)

manifest = SubagentManifest(
    name="consistency_reviewer",
    label="一致性审查",
    description="统一检查设定、人物、时间线、因果、状态连续性和伏笔。",
    non_responsibilities=("不直接重写正文", "不与叙事或文风审查合并"),
    input_schema=ConsistencyReviewInput,
    output_schema=ConsistencyReviewOutput,
    artifact_types=frozenset({"consistency_review"}),
    model_role="consistency_reviewer",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {
            "canon_evidence_report",
            "worldbuilding_proposal",
            "character_proposal",
            "story_architecture",
            "scene_plan",
            "manuscript_candidate",
            "revision_candidate",
        }
    ),
)


async def run(
    input_data: BaseModel, invocation: InvocationContext, context: CapabilityContext
) -> BaseModel:
    return await execute(manifest, input_data, invocation, context)
