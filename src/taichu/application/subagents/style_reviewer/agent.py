"""文风与语言审查专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import StyleReviewInput, StyleReviewOutput

manifest = SubagentManifest(
    name="style_reviewer",
    label="文风与语言审查",
    description="检查措辞、句式、重复、视角、人物口吻和文风一致性。",
    non_responsibilities=("不直接重写正文", "不承担情节或设定审查"),
    input_schema=StyleReviewInput,
    output_schema=StyleReviewOutput,
    artifact_types=frozenset({"style_review"}),
    model_role="style_reviewer",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset(
        {"character_proposal", "manuscript_candidate", "revision_candidate"}
    ),
)


async def run(
    input_data: BaseModel, invocation: InvocationContext, context: CapabilityContext
) -> BaseModel:
    return await execute(manifest, input_data, invocation, context)
