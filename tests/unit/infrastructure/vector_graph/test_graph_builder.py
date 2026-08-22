from langchain_core.documents import Document

from taichu.infrastructure.vector_graph.graph_builder import (
    TaichuChineseGraphBuilder,
    normalize_graph_phrase,
)


def test_normalize_graph_phrase_preserves_chinese_and_collapses_punctuation() -> None:
    assert normalize_graph_phrase("秦浩轩，  修炼！") == "秦浩轩 修炼"


def test_builder_does_not_collapse_distinct_chinese_triplets() -> None:
    builder = TaichuChineseGraphBuilder()
    documents = [
        Document(
            id="passage-1",
            page_content="正文一",
            metadata={"triplets": [["秦浩轩", "修炼", "道心种魔大法"]]},
        ),
        Document(
            id="passage-2",
            page_content="正文二",
            metadata={"triplets": [["张狂", "敌视", "秦浩轩"]]},
        ),
    ]

    builder.build_from_documents(documents)

    assert set(builder.get_entity_texts()) == {"秦浩轩", "道心种魔大法", "张狂"}
    assert set(builder.get_relation_texts()) == {
        "秦浩轩 修炼 道心种魔大法",
        "张狂 敌视 秦浩轩",
    }
