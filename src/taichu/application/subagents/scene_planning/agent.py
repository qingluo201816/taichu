"""章节与场景规划专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import ScenePlanningInput, ScenePlanningOutput

manifest = SubagentManifest(
    name="scene_planning",
    label="章节与场景规划",
    description="把章节目标拆成视角、场景节拍、信息释放和转场。",
    non_responsibilities=("不承担跨卷宏观架构", "不直接生成完整正文"),
    input_schema=ScenePlanningInput,
    output_schema=ScenePlanningOutput,
    artifact_types=frozenset({"scene_plan"}),
    model_role="scene_planning",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {
            "canon_evidence_report",
            "narrative_summary",
            "worldbuilding_proposal",
            "character_proposal",
            "story_architecture",
        }
    ),
)


async def run(
    input_data: BaseModel, invocation: InvocationContext, context: CapabilityContext
) -> BaseModel:
    return await execute(manifest, input_data, invocation, context)
