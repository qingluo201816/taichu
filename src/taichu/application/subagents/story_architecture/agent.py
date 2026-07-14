"""宏观剧情架构专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import (
    StoryArchitectureInput,
    StoryArchitectureOutput,
)

manifest = SubagentManifest(
    name="story_architecture",
    label="宏观剧情架构",
    description="规划卷级、阶段级和跨章节的主支线、升级和伏笔依赖。",
    non_responsibilities=("不拆成逐场景节拍", "不直接生成完整正文"),
    input_schema=StoryArchitectureInput,
    output_schema=StoryArchitectureOutput,
    artifact_types=frozenset({"story_architecture"}),
    model_role="story_architecture",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {
            "canon_evidence_report",
            "external_research_report",
            "narrative_summary",
            "worldbuilding_proposal",
            "character_proposal",
        }
    ),
)


async def run(
    input_data: BaseModel, invocation: InvocationContext, context: CapabilityContext
) -> BaseModel:
    return await execute(manifest, input_data, invocation, context)
