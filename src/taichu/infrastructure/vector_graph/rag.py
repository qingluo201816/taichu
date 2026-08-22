"""强制增量写入使用太初中文安全 GraphBuilder。"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from vector_graph_rag import VectorGraphRAG  # type: ignore[import-untyped]
from vector_graph_rag.models import ExtractionResult  # type: ignore[import-untyped]

from taichu.infrastructure.vector_graph.graph_builder import TaichuChineseGraphBuilder


class TaichuVectorGraphRAG(VectorGraphRAG):
    def upsert_documents_by_source(
        self,
        documents: list[Document],
        source: str | None = None,
        source_field: str = "source",
        metadata: dict[str, Any] | None = None,
        extract_triplets: bool = True,
        show_progress: bool = True,
    ) -> ExtractionResult:
        resolved_source = self._resolve_upsert_source(
            documents,
            source=source,
            source_field=source_field,
            metadata=metadata,
        )
        with self._observed_operation(
            "vgrag.upsert_documents_by_source",
            {
                "vgrag.document_count": len(documents),
                "vgrag.source_field": source_field,
                "vgrag.extract_triplets": extract_triplets,
            },
            source=resolved_source,
        ):
            prepared_documents = self._prepare_upsert_documents(
                resolved_source,
                documents,
                source_field=source_field,
                metadata=metadata,
            )
            if extract_triplets:
                prepared_documents = self._triplet_extractor.extract_from_documents(
                    prepared_documents,
                    show_progress=show_progress,
                )

            builder = TaichuChineseGraphBuilder(settings=self.settings)
            (
                result,
                entity_embeddings,
                relation_embeddings,
                passage_embeddings,
                passage_user_metadatas,
            ) = self._build_graph_records(
                builder,
                prepared_documents,
                show_progress=show_progress,
            )
            self.delete_documents_by_source(
                resolved_source,
                source_field=source_field,
            )
            entity_id_map, relation_id_map = self._insert_incremental_graph(
                builder,
                passage_user_metadatas,
                entity_embeddings,
                relation_embeddings,
                passage_embeddings,
                source=resolved_source,
                source_field=source_field,
                show_progress=show_progress,
            )
            self._extraction_result = self._remap_extraction_result(
                result,
                entity_id_map=entity_id_map,
                relation_id_map=relation_id_map,
            )
            self._retriever = None
            return self._extraction_result
