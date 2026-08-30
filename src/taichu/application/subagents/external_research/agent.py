"""外部资料研究专业子 Agent 插件。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents._factory import EXTERNAL_RESEARCH_TOOLS, execute
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.models import (
    ExternalResearchInput,
    ExternalResearchOutput,
)

manifest = SubagentManifest(
    name="external_research",
    label="外部资料研究",
    description="在用户明确授权后搜索、读取并综合外部来源。",
    non_responsibilities=("不默认联网", "不把外部资料写成小说事实"),
    input_schema=ExternalResearchInput,
    output_schema=ExternalResearchOutput,
    artifact_types=frozenset({"external_research_report"}),
    model_role="external_research",
    allowed_tools=EXTERNAL_RESEARCH_TOOLS,
)


async def run(
    runtime_manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    return await execute(runtime_manifest, input_data, invocation, context)
