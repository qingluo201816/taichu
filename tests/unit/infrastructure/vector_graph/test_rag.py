from contextlib import nullcontext
from unittest.mock import Mock

from langchain_core.documents import Document

from taichu.infrastructure.vector_graph.graph_builder import TaichuChineseGraphBuilder
from taichu.infrastructure.vector_graph.rag import TaichuVectorGraphRAG


def test_incremental_upsert_uses_chinese_graph_builder() -> None:
    rag = object.__new__(TaichuVectorGraphRAG)
    rag.settings = Mock()
    document = Document(
        page_content="秦浩轩修炼道心种魔大法。",
        metadata={
            "source": "chapter-1",
            "triplets": [["秦浩轩", "修炼", "道心种魔大法"]],
        },
    )
    rag._resolve_upsert_source = Mock(return_value="chapter-1")
    rag._observed_operation = Mock(return_value=nullcontext())
    rag._prepare_upsert_documents = Mock(return_value=[document])
    rag._build_graph_records = Mock(return_value=(Mock(), [], [], [], {}))
    rag.delete_documents_by_source = Mock()
    rag._insert_incremental_graph = Mock(return_value=({}, {}))
    rag._remap_extraction_result = Mock(return_value=Mock())

    rag.upsert_documents_by_source(
        [document],
        source="chapter-1",
        extract_triplets=False,
        show_progress=False,
    )

    builder = rag._build_graph_records.call_args.args[0]
    assert isinstance(builder, TaichuChineseGraphBuilder)
