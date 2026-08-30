"""Prompt construction for the chapter summary workflow."""

from taichu.domain.models.knowledge import KnowledgeCard


def build_summary_prompt(
    *,
    chapter_id: str,
    chapter_title: str,
    segments: list[str],
    confirmed_knowledge: list[KnowledgeCard],
) -> str:
    """Build the business prompt for one chapter summary draft."""
    knowledge_lines = [
        f"- {card.name}: {card.summary}" for card in confirmed_knowledge[:20]
    ]
    segment_lines = [
        f"[分段 {index + 1}/{len(segments)}]\n{segment}"
        for index, segment in enumerate(segments)
    ]
    return "\n\n".join(
        [
            "你是太初的章节整理工作流。",
            "只生成章节整理草稿，不写 Knowledge，不确认设定。",
            "正文出现的新设定只能列为待确认候选，不能写成已经确认的小说事实。",
            f"章节 ID：{chapter_id}",
            f"章节标题：{chapter_title}",
            "已确认知识：\n" + ("\n".join(knowledge_lines) or "无"),
            "章节正文分段：\n" + "\n\n".join(segment_lines),
        ]
    )
