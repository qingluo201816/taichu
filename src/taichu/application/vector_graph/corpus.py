"""把正文 Markdown 与已确认知识卡投影成 Vector Graph RAG 来源文档。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from taichu.application.vector_graph.models import (
    VectorGraphSourceDocument,
    VectorGraphSourceIndexState,
    VectorGraphSourceType,
)
from taichu.domain.models.chapter import Chapter
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    knowledge_type_label,
    knowledge_type_schema,
)


@dataclass(frozen=True, slots=True)
class MarkdownChunk:
    content: str
    start_char: int
    end_char: int


_KNOWLEDGE_CONTEXT_SUMMARY_MAX_CHARS = 1_200


def chunk_chapter_markdown(
    markdown: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[MarkdownChunk]:
    """优先沿 Markdown 标题和段落边界切分，并保留稳定字符位置。"""
    if chunk_size < 100:
        raise ValueError("正文向量切片长度不能小于 100。")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("正文向量切片重叠必须大于等于零且小于切片长度。")
    if not markdown.strip():
        return []

    boundaries = _semantic_boundaries(markdown)
    chunks: list[MarkdownChunk] = []
    cursor = 0
    while cursor < len(markdown):
        hard_end = min(len(markdown), cursor + chunk_size)
        end = _aligned_chunk_end(
            markdown,
            boundaries=boundaries,
            cursor=cursor,
            hard_end=hard_end,
            chunk_size=chunk_size,
        )
        if end <= cursor:
            end = hard_end
        raw = markdown[cursor:end]
        left_trim = len(raw) - len(raw.lstrip())
        right_trim = len(raw.rstrip())
        start_char = cursor + left_trim
        end_char = cursor + right_trim
        if end_char > start_char:
            chunks.append(
                MarkdownChunk(
                    content=markdown[start_char:end_char],
                    start_char=start_char,
                    end_char=end_char,
                )
            )
        if end >= len(markdown):
            break
        cursor = _aligned_overlap_start(
            markdown,
            previous_cursor=cursor,
            end=end,
            chunk_overlap=chunk_overlap,
        )
    return chunks


def project_chapter(
    chapter: Chapter,
    markdown: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[VectorGraphSourceDocument]:
    chunks = chunk_chapter_markdown(
        markdown,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    documents: list[VectorGraphSourceDocument] = []
    for index, chunk in enumerate(chunks):
        parent_indexes = list(range(max(0, index - 1), min(len(chunks), index + 2)))
        parent_chunks = [chunks[item] for item in parent_indexes]
        documents.append(
            VectorGraphSourceDocument(
                source_type=VectorGraphSourceType.MANUSCRIPT_CHUNK,
                source_id=chapter.id,
                source_ref=(
                    f"manuscript:{chapter.id}:{chunk.start_char}-{chunk.end_char}"
                ),
                title=chapter.title,
                content=chunk.content,
                content_sha256=_sha256(chunk.content),
                updated_at=chapter.updated_at,
                chunk_index=index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                parent_start_char=parent_chunks[0].start_char,
                parent_end_char=parent_chunks[-1].end_char,
                parent_chunk_indexes=parent_indexes,
            )
        )
    return documents


def project_knowledge_card(
    card: StructuredKnowledgeCard,
    card_lookup: dict[str, StructuredKnowledgeCard],
) -> VectorGraphSourceDocument:
    """每张知识卡只形成一个完整 passage，避免字段切片割裂事实。"""
    lines = [
        f"知识类型：{knowledge_type_label(card.type)}",
        f"名称：{card.name.strip()}",
    ]
    if card.aliases:
        lines.append("别名：" + "、".join(_unique_strings(card.aliases)))
    lines.append(f"摘要：{card.summary.strip()}")
    for schema in knowledge_type_schema(card.type).fields:
        if schema.display_group != "类型字段":
            continue
        value = _render_value(getattr(card, schema.field_key), card_lookup)
        if value:
            lines.append(f"{schema.label}：{value}")
    lines.extend(
        [
            f"来源方式：{card.source_origin.value if card.source_origin else ''}",
            f"来源说明：{card.source_note.strip()}",
        ]
    )
    content = "\n".join(line for line in lines if not line.endswith("："))
    return VectorGraphSourceDocument(
        source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
        source_id=card.id,
        source_ref=f"knowledge:{card.id}",
        title=card.name.strip(),
        content=content,
        content_sha256=_sha256(content),
        updated_at=card.updated_at,
    )


def compact_knowledge_card_context(content: str) -> str:
    """为模型投影知识卡业务字段，不携带长来源附录。"""

    output: list[str] = []
    for line in content.splitlines():
        if line.startswith(("来源方式：", "来源说明：")):
            break
        if line.startswith("摘要："):
            prefix = "摘要："
            summary = line.removeprefix(prefix)
            if len(summary) > _KNOWLEDGE_CONTEXT_SUMMARY_MAX_CHARS:
                line = (
                    prefix
                    + summary[:_KNOWLEDGE_CONTEXT_SUMMARY_MAX_CHARS]
                    + "…"
                )
        output.append(line)
    return "\n".join(output).strip()


def corpus_snapshot_sha256(documents: list[VectorGraphSourceDocument]) -> str:
    """计算有业务意义的全局快照；仅更新时间变化不会令索引过期。"""
    payload = [
        document.model_dump(mode="json", exclude={"updated_at"})
        for document in sorted(
            documents,
            key=lambda item: (item.source_type.value, item.source_id, item.chunk_index),
        )
    ]
    return _sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def source_key(document: VectorGraphSourceDocument) -> str:
    """返回跨重试稳定的业务来源标识，不依赖文件路径或标题。"""
    return f"{document.source_type.value}:{document.source_id}"


def group_source_documents(
    documents: list[VectorGraphSourceDocument],
) -> dict[str, list[VectorGraphSourceDocument]]:
    grouped: dict[str, list[VectorGraphSourceDocument]] = {}
    for document in documents:
        grouped.setdefault(source_key(document), []).append(document)
    return {
        key: sorted(items, key=lambda item: item.chunk_index)
        for key, items in sorted(grouped.items())
    }


def source_documents_sha256(
    documents: list[VectorGraphSourceDocument],
    *,
    index_configuration_sha256: str,
) -> str:
    """计算来源投影哈希；更新时间变化但实际投影未变时不会重建索引。"""
    payload = {
        "index_configuration_sha256": index_configuration_sha256,
        "documents": [
            document.model_dump(mode="json", exclude={"updated_at"})
            for document in sorted(documents, key=lambda item: item.chunk_index)
        ],
    }
    return _sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def build_source_index_state(
    documents: list[VectorGraphSourceDocument],
    *,
    indexed_at: str,
    index_configuration_sha256: str,
) -> VectorGraphSourceIndexState:
    if not documents:
        raise ValueError("来源索引状态不能由空文档生成。")
    first = documents[0]
    if any(source_key(document) != source_key(first) for document in documents):
        raise ValueError("来源索引状态只能包含同一章节或知识卡。")
    return VectorGraphSourceIndexState(
        source_key=source_key(first),
        source_type=first.source_type,
        source_id=first.source_id,
        source_sha256=source_documents_sha256(
            documents,
            index_configuration_sha256=index_configuration_sha256,
        ),
        index_configuration_sha256=index_configuration_sha256,
        document_count=len(documents),
        total_content_chars=sum(len(document.content) for document in documents),
        source_updated_at=max(document.updated_at for document in documents),
        indexed_at=indexed_at,
    )


def _semantic_boundaries(markdown: str) -> list[int]:
    boundaries = {len(markdown)}
    for match in re.finditer(r"\n\s*\n|\n(?=#{1,6}\s)", markdown):
        boundaries.add(match.end())
    return sorted(boundaries)


def _aligned_chunk_end(
    markdown: str,
    *,
    boundaries: list[int],
    cursor: int,
    hard_end: int,
    chunk_size: int,
) -> int:
    """只在目标长度附近对齐，避免章节开头的短标题单独形成碎片。"""
    if hard_end >= len(markdown):
        return len(markdown)
    minimum_end = cursor + max(1, int(chunk_size * 0.7))
    paragraph_ends = [
        item for item in boundaries if minimum_end <= item <= hard_end
    ]
    if paragraph_ends:
        return max(paragraph_ends)
    sentence_ends = [
        match.end()
        for match in re.finditer(r"[。！？!?][”’」』）》】]*\s*", markdown)
        if minimum_end <= match.end() <= hard_end
    ]
    if sentence_ends:
        return max(sentence_ends)
    return hard_end


def _aligned_overlap_start(
    markdown: str,
    *,
    previous_cursor: int,
    end: int,
    chunk_overlap: int,
) -> int:
    if chunk_overlap == 0:
        return end
    target = end - chunk_overlap
    minimum_overlap = max(1, int(chunk_overlap * 0.7))
    maximum_overlap = max(minimum_overlap, int(chunk_overlap * 1.3))
    lower = max(previous_cursor + 1, end - maximum_overlap)
    upper = min(end - minimum_overlap, len(markdown))
    if lower > upper:
        return max(previous_cursor + 1, target)

    paragraph_starts = [
        match.end()
        for match in re.finditer(r"\n\s*\n|\n(?=#{1,6}\s)", markdown)
        if lower <= match.end() <= upper
    ]
    if paragraph_starts:
        return min(paragraph_starts, key=lambda item: (abs(item - target), item))

    sentence_starts = [
        match.end()
        for match in re.finditer(r"[。！？!?][”’」』）》】]*\s*", markdown)
        if lower <= match.end() <= upper
    ]
    if sentence_starts:
        return min(sentence_starts, key=lambda item: (abs(item - target), item))
    return max(previous_cursor + 1, target)


def _render_value(
    value: Any,
    card_lookup: dict[str, StructuredKnowledgeCard],
) -> str | None:
    if value is None or value == "" or value == []:
        return None
    if isinstance(value, list):
        values = _unique_strings([str(item) for item in value])
        return "、".join(values) or None
    if isinstance(value, bool):
        return "是" if value else "否"
    referenced = card_lookup.get(str(value))
    if referenced is not None:
        return referenced.name
    rendered = str(value).strip()
    return rendered or None


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
