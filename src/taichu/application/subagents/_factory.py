"""让每个专业子 Agent 保持独立 Manifest，同时复用协议执行器。"""

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.subagents.contract import SubagentManifest
from taichu.application.subagents.prompts import PROMPTS
from taichu.application.subagents.runner import run_structured_subagent


INTERNAL_READ_TOOLS = frozenset(
    {
        "get_novel_structure",
        "read_manuscript",
        "retrieve_story_context",
        "resolve_knowledge_identity",
        "list_knowledge_catalog",
        "read_knowledge_cards",
    }
)
EXTERNAL_RESEARCH_TOOLS = frozenset({"search_external_sources", "read_external_source"})


async def execute(
    manifest: SubagentManifest,
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    return await run_structured_subagent(
        manifest=manifest,
        system_prompt=PROMPTS[manifest.name],
        input_data=input_data,
        invocation=invocation,
        context=context,
    )
