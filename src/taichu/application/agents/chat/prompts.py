"""自由对话 Agent 的系统提示词。"""

SYSTEM_PROMPT = """你是一个专注于单本玄幻小说写作的助手，名叫“太初”。
当前系统中只有一部小说，用户提到“主角”“世界观”“当前章节”等内容时，
默认指当前唯一小说，不需要询问用户选择哪部小说。

你可以帮助用户进行以下工作：
- 世界观构建
- 角色设计
- 功法体系设计
- 剧情大纲规划
- 章节写作和润色

用简洁但富有创意的中文回复用户。"""


def build_chat_prompt(
    *,
    message: str,
    chapter_title: str | None,
    chapter_excerpt: str | None,
    confirmed_fact_lines: list[str],
    retrieval_lines: list[str],
) -> str:
    """Build the source-aware prompt for Basic Agent Chat."""
    source_rule = (
        "回答必须区分来源支持与推测。使用提供的章节、confirmed Knowledge、"
        "检索证据时，在句末标注 [S1]、[S2] 等来源编号；没有来源支持的"
        "内容必须写明“以下为推测”。不得把待确认设定、灵感、AI 卡片或"
        "章节摘要当作正式事实。"
    )
    chapter_block = "未选择当前章节"
    if chapter_title and chapter_excerpt:
        chapter_block = f"[S1] 当前章节《{chapter_title}》摘录：\n{chapter_excerpt}"

    source_index = 2 if chapter_title and chapter_excerpt else 1
    fact_block = _numbered_block(
        "confirmed Knowledge", confirmed_fact_lines, source_index
    )
    source_index += len(confirmed_fact_lines)
    retrieval_block = _numbered_block("检索证据", retrieval_lines, source_index)

    return "\n\n".join(
        [
            SYSTEM_PROMPT,
            source_rule,
            chapter_block,
            fact_block,
            retrieval_block,
            f"作者问题：{message}",
        ]
    )


def _numbered_block(label: str, lines: list[str], start: int) -> str:
    if not lines:
        return f"{label}：无"
    numbered = [f"[S{start + index}] {line}" for index, line in enumerate(lines)]
    return f"{label}：\n" + "\n".join(numbered)
