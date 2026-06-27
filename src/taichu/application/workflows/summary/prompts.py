"""Prompt construction for the chapter summary workflow."""

from taichu.domain.models.knowledge import KnowledgeCard
from taichu.domain.models.retrieval import RetrievalHit


def build_summary_prompt(
    *,
    chapter_id: str,
    chapter_title: str,
    segments: list[str],
    confirmed_knowledge: list[KnowledgeCard],
    retrieval_hits: list[RetrievalHit],
) -> str:
    """Build a strict JSON prompt for one chapter summary draft."""
    knowledge_lines = [
        f"- {card.name}: {card.summary}" for card in confirmed_knowledge[:20]
    ]
    evidence_lines = [
        f"- {hit.source_type.value}:{hit.source_id}: {hit.excerpt}"
        for hit in retrieval_hits[:8]
    ]
    segment_lines = [
        f"[分段 {index + 1}/{len(segments)}]\n{segment}"
        for index, segment in enumerate(segments)
    ]
    return "\n\n".join(
        [
            "你是太初的章节整理工作流。",
            "只生成章节整理草稿，不写 Knowledge，不确认设定。",
            (
                "必须只返回 JSON object，不要 Markdown 代码块。JSON 字段："
                "summary, key_events, character_changes, "
                "new_setting_candidates, foreshadow_candidates, next_chapter_hooks。"
            ),
            (
                "new_setting_candidates 的每一项必须包含 "
                "fact_type, title, content；它们只是待确认候选。"
            ),
            f"章节 ID：{chapter_id}",
            f"章节标题：{chapter_title}",
            "已确认知识：\n" + ("\n".join(knowledge_lines) or "无"),
            "检索证据：\n" + ("\n".join(evidence_lines) or "无"),
            "章节正文分段：\n" + "\n\n".join(segment_lines),
        ]
    )
