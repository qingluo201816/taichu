"""在显式许可下搜索外部来源。"""

from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.external_research.service import ExternalResearchService
from taichu.application.invocations.models import InvocationContext
from taichu.application.tools._shared import EXTERNAL_RESEARCH_CALLERS
from taichu.application.tools.contract import ToolManifest
from taichu.application.tools.models import (
    ExternalSearchItem,
    SearchExternalSourcesInput,
    SearchExternalSourcesOutput,
)


manifest = ToolManifest(
    name="search_external_sources",
    description="仅在明确用户许可下搜索小说写作所需的外部资料来源。",
    input_schema=SearchExternalSourcesInput,
    output_schema=SearchExternalSourcesOutput,
    required_capabilities=frozenset({"external_research_service"}),
    exposures=frozenset({"agent_runtime"}),
    allowed_callers=EXTERNAL_RESEARCH_CALLERS,
    requires_external_access=True,
    default_timeout_seconds=30,
    retryable=True,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = SearchExternalSourcesInput.model_validate(input_data)
    additions = [*tool_input.source_preferences]
    if tool_input.date_range:
        additions.append(tool_input.date_range)
    query = " ".join([tool_input.query, *additions]).strip()
    results = await context.require(
        "external_research_service",
        ExternalResearchService,
    ).search(query, max_results=tool_input.max_results)
    search_id = f"external_search_{uuid4().hex}"
    items = [
        ExternalSearchItem(
            title=item.title,
            url=item.url,
            domain=item.domain or (urlparse(item.url).hostname or "未知来源"),
            snippet=item.snippet,
            published_at=item.published_at,
        )
        for item in results
    ]
    return SearchExternalSourcesOutput(
        search_id=search_id,
        query=query,
        items=items,
        source_refs=[item.url for item in items],
    )
