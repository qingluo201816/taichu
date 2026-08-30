"""角色与关系专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import CharacterInput, CharacterOutput

manifest = SubagentManifest(
    name="character",
    label="角色设定与关系",
    description="维护人物动机、性格、能力、关系、成长和行为边界。",
    non_responsibilities=("不直接写入知识库", "不承担宏观剧情规划"),
    input_schema=CharacterInput,
    output_schema=CharacterOutput,
    artifact_types=frozenset({"character_proposal", "knowledge_proposal"}),
    model_role="character",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {
            "canon_evidence_report",
            "external_research_report",
            "narrative_summary",
            "worldbuilding_proposal",
        }
    ),
)


async def run(
    runtime_manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    return await execute(runtime_manifest, input_data, invocation, context)
