"""通过本地 Hugging Face TEI 服务调用 BGE 二阶段重排模型。"""

from __future__ import annotations

import asyncio

import httpx

from taichu.application.vector_graph.models import VectorGraphEvidence


_MAX_CLIENT_BATCH_SIZE = 64


class BGEReranker:
    def __init__(self, *, base_url: str, model_id: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        # 单批最多占满本地 TEI 的推理许可；仅对重排 HTTP 批次排队，
        # 不限制上层 Agent、检索或模型调用的并行度。
        self._inference_lock = asyncio.Lock()

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
        async with (
            asyncio.timeout(self.timeout_seconds),
            httpx.AsyncClient(timeout=self.timeout_seconds) as client,
        ):
            for offset in range(0, len(texts), _MAX_CLIENT_BATCH_SIZE):
                async with self._inference_lock:
                    response = await self._request_batch(
                        client, query, texts[offset : offset + _MAX_CLIENT_BATCH_SIZE],
                    )
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

    async def _request_batch(
        self, client: httpx.AsyncClient, query: str, texts: list[str],
    ) -> httpx.Response:
        for attempt in range(3):
            response = await client.post(
                f"{self.base_url}/rerank",
                json={"query": query, "texts": texts, "raw_scores": False},
            )
            if response.status_code != 429 or attempt == 2:
                response.raise_for_status()
                return response
            # 只重试过载，整个排队、请求及退避过程仍受外层总超时约束。
            delay = 0.25 * (2 ** attempt)
            try:
                delay = max(delay, float(response.headers.get("Retry-After", "0")))
            except ValueError:
                pass
            await asyncio.sleep(delay)
        raise AssertionError("重排请求未按有限重试策略结束。")


def _reranker_text(evidence: VectorGraphEvidence) -> str:
    """给 BGE 一个有界、关系可见的 Passage 表示。"""

    relation_context = "；".join(evidence.relation_texts[:12])
    sections = [f"标题：{evidence.title}"]
    if relation_context:
        sections.append(f"图关系：{relation_context}")
    sections.append("正文：" + evidence.content[:4_000])
    return "\n".join(sections)
