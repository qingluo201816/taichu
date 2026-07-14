"""对当前 Markdown 正文执行确定性词法搜索。"""

import re

from pydantic import BaseModel

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.chapter_service import ChapterService
from taichu.application.tools._shared import INTERNAL_READ_CALLERS
from taichu.application.tools.contract import ToolManifest
from taichu.application.tools.models import (
    ManuscriptSearchHit,
    SearchManuscriptInput,
    SearchManuscriptOutput,
)


manifest = ToolManifest(
    name="search_manuscript",
    description="在未知位置时对当前小说 Markdown 正文执行确定性词法搜索。",
    input_schema=SearchManuscriptInput,
    output_schema=SearchManuscriptOutput,
    required_capabilities=frozenset({"chapter_service"}),
    exposures=frozenset({"agent_runtime"}),
    allowed_callers=INTERNAL_READ_CALLERS,
    retryable=True,
)


async def run(
    input_data: BaseModel,
    invocation: InvocationContext,
    context: CapabilityContext,
) -> BaseModel:
    del invocation
    tool_input = SearchManuscriptInput.model_validate(input_data)
    service = context.require("chapter_service", ChapterService)
    chapter_ids = set(tool_input.chapter_ids)
    volume_ids = set(tool_input.volume_ids)
    terms = _query_terms(tool_input.query)
    candidates: list[ManuscriptSearchHit] = []
    scanned = 0
    for chapter in await service.list_chapters():
        if chapter_ids and chapter.id not in chapter_ids:
            continue
        if volume_ids and chapter.volume_id not in volume_ids:
            continue
        content = await service.read_chapter(chapter.id)
        scanned += 1
        lowered = content.markdown.casefold()
        positions = [lowered.find(term.casefold()) for term in terms]
        positions = [position for position in positions if position >= 0]
        if not positions:
            continue
        start = min(positions)
        left = max(0, start - tool_input.excerpt_chars // 2)
        right = min(len(content.markdown), left + tool_input.excerpt_chars)
        exact_count = lowered.count(tool_input.query.casefold())
        term_hits = sum(lowered.count(term.casefold()) for term in terms)
        score = float(exact_count * 10 + term_hits)
        reasons = []
        if exact_count:
            reasons.append("查询原文完整命中")
        if term_hits:
            reasons.append(f"查询词累计命中 {term_hits} 次")
        candidates.append(
            ManuscriptSearchHit(
                chapter_id=chapter.id,
                title=chapter.title,
                order=chapter.order,
                start_char=left,
                end_char=right,
                excerpt=content.markdown[left:right],
                score=score,
                match_reasons=reasons,
                source_ref=f"manuscript:{chapter.id}:{left}-{right}",
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.order, item.start_char))
    hits = candidates[: tool_input.max_hits]
    return SearchManuscriptOutput(
        query=tool_input.query,
        scanned_chapters=scanned,
        hits=hits,
        truncated=len(candidates) > len(hits),
        source_refs=[item.source_ref for item in hits],
    )


def _query_terms(query: str) -> list[str]:
    normalized = query.strip()
    terms = [normalized]
    terms.extend(
        token
        for token in re.findall(r"[\w\u3400-\u4dbf\u4e00-\u9fff]+", normalized)
        if len(token) >= 2 and token != normalized
    )
    return list(dict.fromkeys(terms))
