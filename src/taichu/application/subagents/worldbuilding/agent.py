"""世界观设计专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import WorldbuildingInput, WorldbuildingOutput

manifest = SubagentManifest(
    name="worldbuilding",
    label="世界观与设定设计",
    description="设计世界规则、境界、功法、势力、地点和物品草案。",
    non_responsibilities=("不直接写入知识库", "不承担完整正文生成"),
    input_schema=WorldbuildingInput,
    output_schema=WorldbuildingOutput,
    artifact_types=frozenset({"worldbuilding_proposal", "knowledge_proposal"}),
    model_role="worldbuilding",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {"canon_evidence_report", "external_research_report", "narrative_summary"}
    ),
)


async def run(
    runtime_manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    return await execute(runtime_manifest, input_data, invocation, context)
