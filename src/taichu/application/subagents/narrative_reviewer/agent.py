"""叙事质量审查专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import (
    NarrativeReviewInput,
    NarrativeReviewOutput,
)

manifest = SubagentManifest(
    name="narrative_reviewer",
    label="叙事质量审查",
    description="检查节奏、冲突、信息释放、悬念、转折和理解成本。",
    non_responsibilities=("不直接重写正文", "不承担文风或设定一致性审查"),
    input_schema=NarrativeReviewInput,
    output_schema=NarrativeReviewOutput,
    artifact_types=frozenset({"narrative_review"}),
    model_role="narrative_reviewer",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {
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
