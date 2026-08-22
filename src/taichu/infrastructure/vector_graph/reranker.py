"""通过本地 Hugging Face TEI 服务调用 BGE 二阶段重排模型。"""

from __future__ import annotations

import httpx

from taichu.application.vector_graph.models import VectorGraphEvidence


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
        texts = [f"{item.title}\n{item.content}" for item in evidences]
        scored: list[tuple[float, int]] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for offset in range(0, len(texts), 32):
                response = await client.post(
                    f"{self.base_url}/rerank",
                    json={
                        "query": query,
                        "texts": texts[offset : offset + 32],
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
        for _score, index in scored[:top_k]:
            output.append(evidences[index].model_copy(update={"rank": len(output) + 1}))
        return output
