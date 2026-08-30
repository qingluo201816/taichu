"""叙事摘要专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import INTERNAL_READ_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import (
    NarrativeSummaryInput,
    NarrativeSummaryOutput,
)

manifest = SubagentManifest(
    name="narrative_summary",
    label="叙事摘要",
    description="忠实归纳章节、人物经历和事件阶段。",
    non_responsibilities=("不补写情节", "不读取创作工作区摘要"),
    input_schema=NarrativeSummaryInput,
    output_schema=NarrativeSummaryOutput,
    artifact_types=frozenset({"narrative_summary"}),
    model_role="narrative_summary",
    allowed_tools=INTERNAL_READ_TOOLS,
    accepted_artifact_types=frozenset({"canon_evidence_report"}),
)


async def run(
    runtime_manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    return await execute(runtime_manifest, input_data, invocation, context)
