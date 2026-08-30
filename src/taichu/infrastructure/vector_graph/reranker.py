"""通过本地 Hugging Face TEI 服务调用 BGE 二阶段重排模型。"""

from __future__ import annotations

import httpx

from taichu.application.vector_graph.models import VectorGraphEvidence


_MAX_CLIENT_BATCH_SIZE = 64


class BGEReranker:
    def __init__(self, *, base_url: str, model_id: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds

    async def rerank(
        self,
        query: str,
        evidences: list[VectorGraphEvidence],
        *,
        top_k: int,
    ) -> list[VectorGraphEvidence]:
        if not evidences:
            return []
        texts = [_reranker_text(item) for item in evidences]
        scored: list[tuple[float, int]] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for offset in range(0, len(texts), _MAX_CLIENT_BATCH_SIZE):
                response = await client.post(
                    f"{self.base_url}/rerank",
                    json={
                        "query": query,
                        "texts": texts[offset : offset + _MAX_CLIENT_BATCH_SIZE],
                        "raw_scores": False,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                ranked = (
                    payload if isinstance(payload, list) else payload.get("results", [])
                )
                scored.extend(
                    (float(item["score"]), offset + int(item["index"]))
                    for item in ranked
                )
        scored.sort(key=lambda item: (-item[0], item[1]))
        output: list[VectorGraphEvidence] = []
        for score, index in scored[:top_k]:
            output.append(
                evidences[index].model_copy(
                    update={
                        "rank": len(output) + 1,
                        "reranker_score": score,
                    }
                )
            )
        return output


def _reranker_text(evidence: VectorGraphEvidence) -> str:
    """给 BGE 一个有界、关系可见的 Passage 表示。"""

    relation_context = "；".join(evidence.relation_texts[:12])
    sections = [f"标题：{evidence.title}"]
    if relation_context:
        sections.append(f"图关系：{relation_context}")
    sections.append("正文：" + evidence.content[:4_000])
    return "\n".join(sections)
