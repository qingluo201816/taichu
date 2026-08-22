"""正文与知识卡 Vector Graph RAG 投影测试。"""

import hashlib

from taichu.application.vector_graph.corpus import (
    corpus_snapshot_sha256,
    chunk_chapter_markdown,
    group_source_documents,
    project_chapter,
    source_documents_sha256,
)
from taichu.application.vector_graph.models import (
    VectorGraphSourceDocument,
    VectorGraphSourceType,
)
from taichu.domain.models.chapter import Chapter, ChapterStatus


def test_markdown_chunking_is_deterministic_and_preserves_source_spans() -> None:
    markdown = "# 第一节\n\n" + "甲" * 180 + "\n\n## 第二节\n\n" + "乙" * 180

    chunks = chunk_chapter_markdown(
        markdown,
        chunk_size=220,
        chunk_overlap=40,
    )

    assert len(chunks) >= 2
    assert all(
        markdown[item.start_char : item.end_char] == item.content for item in chunks
    )
    assert chunks == chunk_chapter_markdown(
        markdown,
        chunk_size=220,
        chunk_overlap=40,
    )


def test_markdown_chunking_rejects_invalid_overlap() -> None:
    try:
        chunk_chapter_markdown("正文", chunk_size=100, chunk_overlap=100)
    except ValueError as error:
        assert "重叠" in str(error)
    else:
        raise AssertionError("无效重叠没有被拒绝")


def test_overlap_start_prefers_complete_sentence_near_target() -> None:
    markdown = ("甲" * 48 + "。") * 10

    chunks = chunk_chapter_markdown(
        markdown,
        chunk_size=200,
        chunk_overlap=50,
    )

    assert len(chunks) >= 2
    assert chunks[1].start_char == 147
    assert markdown[chunks[1].start_char - 1] == "。"
    assert markdown[chunks[0].end_char - 1] == "。"
    assert 35 <= chunks[0].end_char - chunks[1].start_char <= 65


def test_early_heading_boundary_does_not_create_repeated_tiny_chunks() -> None:
    markdown = "# 第七章 淡然明鉴道初心\n\n" + "甲" * 1_000

    chunks = chunk_chapter_markdown(
        markdown,
        chunk_size=220,
        chunk_overlap=40,
    )

    assert len(chunks[0].content) >= 154
    assert all(len(item.content) >= 154 for item in chunks[:-1])
    assert len({(item.start_char, item.end_char) for item in chunks}) == len(chunks)
    assert chunks[0].content.startswith("# 第七章 淡然明鉴道初心")


def test_each_child_records_three_chunk_parent_range_without_crossing_edges() -> None:
    markdown = ("甲" * 48 + "。") * 14
    chapter = Chapter(
        id="chapter-1",
        title="第一章",
        order=0,
        markdown_path="chapters/1.md",
        status=ChapterStatus.ACTIVE,
        word_count=len(markdown),
        created_at="2026-08-15T00:00:00Z",
        updated_at="2026-08-15T00:00:00Z",
    )

    documents = project_chapter(
        chapter,
        markdown,
        chunk_size=200,
        chunk_overlap=50,
    )

    assert documents[0].parent_chunk_indexes == [0, 1]
    assert documents[1].parent_chunk_indexes == [0, 1, 2]
    assert documents[-1].parent_chunk_indexes == [
        len(documents) - 2,
        len(documents) - 1,
    ]
    assert documents[1].parent_start_char == documents[0].start_char
    assert documents[1].parent_end_char == documents[2].end_char


def test_global_and_source_hashes_ignore_updated_at_but_track_projection_changes() -> (
    None
):
    documents = [
        _source_document(
            source_id="chapter-1",
            chunk_index=0,
            title="第一章",
            content="秦浩轩进入灵田谷。",
        ),
        _source_document(
            source_id="chapter-1",
            chunk_index=1,
            title="第一章",
            content="他发现了一株灵药。",
        ),
    ]
    configuration_sha256 = "c" * 64
    global_sha256 = corpus_snapshot_sha256(documents)
    source_sha256 = source_documents_sha256(
        documents,
        index_configuration_sha256=configuration_sha256,
    )

    touched_documents = [
        document.model_copy(update={"updated_at": "2026-08-16T12:00:00Z"})
        for document in documents
    ]
    assert corpus_snapshot_sha256(touched_documents) == global_sha256
    assert (
        source_documents_sha256(
            touched_documents,
            index_configuration_sha256=configuration_sha256,
        )
        == source_sha256
    )

    changed_variants = [
        [
            documents[0],
            _source_document(
                source_id="chapter-1",
                chunk_index=1,
                title="第一章",
                content="他发现了两株灵药。",
            ),
        ],
        [
            documents[0].model_copy(update={"title": "第一章 灵田谷"}),
            documents[1],
        ],
        [
            _source_document(
                source_id="chapter-1",
                chunk_index=0,
                title="第一章",
                content="秦浩轩进入灵田谷。他发现了一株灵药。",
                source_ref="manuscript:chapter-1:0-19",
            )
        ],
    ]
    for changed_documents in changed_variants:
        assert corpus_snapshot_sha256(changed_documents) != global_sha256
        assert (
            source_documents_sha256(
                changed_documents,
                index_configuration_sha256=configuration_sha256,
            )
            != source_sha256
        )

    assert (
        source_documents_sha256(
            documents,
            index_configuration_sha256="d" * 64,
        )
        != source_sha256
    )


def test_source_grouping_is_stably_sorted_by_source_and_chunk() -> None:
    chapter_1_chunk_0 = _source_document(source_id="chapter-1", chunk_index=0)
    chapter_1_chunk_1 = _source_document(source_id="chapter-1", chunk_index=1)
    chapter_2_chunk_0 = _source_document(source_id="chapter-2", chunk_index=0)

    grouped = group_source_documents(
        [chapter_2_chunk_0, chapter_1_chunk_1, chapter_1_chunk_0]
    )

    assert list(grouped) == [
        "manuscript_chunk:chapter-1",
        "manuscript_chunk:chapter-2",
    ]
    assert grouped["manuscript_chunk:chapter-1"] == [
        chapter_1_chunk_0,
        chapter_1_chunk_1,
    ]


def _source_document(
    *,
    source_id: str,
    chunk_index: int,
    title: str = "章节",
    content: str = "正文",
    source_ref: str | None = None,
) -> VectorGraphSourceDocument:
    return VectorGraphSourceDocument(
        source_type=VectorGraphSourceType.MANUSCRIPT_CHUNK,
        source_id=source_id,
        source_ref=source_ref
        or f"manuscript:{source_id}:{chunk_index * 10}-{chunk_index * 10 + len(content)}",
        title=title,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        updated_at="2026-08-15T00:00:00Z",
        chunk_index=chunk_index,
        start_char=chunk_index * 10,
        end_char=chunk_index * 10 + len(content),
    )
