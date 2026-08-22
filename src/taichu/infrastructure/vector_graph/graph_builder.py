"""保留中文实体与谓词的 Vector Graph 构建器。"""

from __future__ import annotations

import re

from vector_graph_rag.graph.builder import (  # type: ignore[import-untyped]
    GraphBuilder,
    Triplet,
    generate_id,
)


class TaichuChineseGraphBuilder(GraphBuilder):
    """替代上游仅保留 ASCII 字符的短语规范化。"""

    def _add_entity(self, entity_name: str, passage_id: str) -> str:
        normalized = normalize_graph_phrase(entity_name)
        if not normalized:
            raise ValueError("三元组实体规范化后不得为空。")
        if normalized not in self.entity_name_to_id:
            entity_id = generate_id()
            self.entities[entity_id] = normalized
            self.entity_ids.append(entity_id)
            self.entity_name_to_id[normalized] = entity_id

        entity_id = self.entity_name_to_id[normalized]
        if passage_id not in self.entity_to_passage_ids[entity_id]:
            self.entity_to_passage_ids[entity_id].append(passage_id)
        if entity_id not in self.passage_to_entity_ids[passage_id]:
            self.passage_to_entity_ids[passage_id].append(entity_id)
        return entity_id

    def _add_relation(self, triplet: Triplet, passage_id: str) -> str:
        subject = normalize_graph_phrase(triplet.subject)
        predicate = normalize_graph_phrase(triplet.predicate)
        object_ = normalize_graph_phrase(triplet.object)
        if not subject or not predicate or not object_:
            raise ValueError("三元组主体、谓词和客体规范化后都不得为空。")
        relation_text = f"{subject} {predicate} {object_}"

        if relation_text not in self.relation_text_to_id:
            relation_id = generate_id()
            self.relations[relation_id] = relation_text
            self.relation_ids.append(relation_id)
            self.relation_text_to_id[relation_text] = relation_id
            self.relation_id_to_triplet[relation_id] = Triplet(
                subject=subject,
                predicate=predicate,
                object=object_,
            )
            subject_id = self._add_entity(subject, passage_id)
            object_id = self._add_entity(object_, passage_id)
            self.entity_to_relation_ids[subject_id].append(relation_id)
            self.entity_to_relation_ids[object_id].append(relation_id)
            self.relation_to_entity_ids[relation_id] = [subject_id, object_id]

        relation_id = self.relation_text_to_id[relation_text]
        if passage_id not in self.relation_to_passage_ids[relation_id]:
            self.relation_to_passage_ids[relation_id].append(passage_id)
        if relation_id not in self.passage_to_relation_ids[passage_id]:
            self.passage_to_relation_ids[passage_id].append(relation_id)
        return relation_id


def normalize_graph_phrase(value: str) -> str:
    """保留 Unicode 字母与数字，仅将标点和多余空白归一化。"""
    normalized = "".join(
        character if character.isalnum() else " " for character in value.casefold()
    )
    return re.sub(r"\s+", " ", normalized).strip()
