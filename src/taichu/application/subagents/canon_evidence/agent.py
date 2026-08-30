"""小说事实证据专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import CanonEvidenceInput, CanonEvidenceOutput

manifest = SubagentManifest(
    name="canon_evidence",
    label="小说事实证据",
    description="回答小说内部事实、定位原文证据并呈现冲突和未知。",
    non_responsibilities=("不创作新设定", "不改写正文"),
    input_schema=CanonEvidenceInput,
    output_schema=CanonEvidenceOutput,
    artifact_types=frozenset({"canon_evidence_report"}),
    model_role="canon_evidence",
    allowed_tools=INTERNAL_READ_TOOLS,
)


async def run(
    runtime_manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    return await execute(runtime_manifest, input_data, invocation, context)
