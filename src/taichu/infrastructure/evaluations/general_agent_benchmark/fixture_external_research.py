"""密封评测夹具专用外部资料后端；不包含任何网络能力。"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from taichu.application.external_research.models import (
    ExternalDocument,
    ExternalSearchResult,
)

_FIXTURE_ORIGIN = "https://fixture.invalid"


class FixtureExternalResearchBackend:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=True)
        payload = json.loads((self._root / "manifest.json").read_text(encoding="utf-8"))
        sources = payload.get("sources")
        if not isinstance(sources, list):
            raise ValueError("合成外部资料 manifest.sources 必须是数组。")
        self._sources = tuple(_validate_source(self._root, item) for item in sources)
        self._by_url = {
            _source_url(str(item["source_id"])): item for item in self._sources
        }
        self._operation_count = 0

    @property
    def audit_identity(self) -> str:
        return "taichu.fixture_external_research.local_files@1"

    @property
    def network_attempt_count(self) -> int:
        """该实现没有网络传输端口；计数固定表达可审计能力边界。"""
        return 0

    @property
    def operation_count(self) -> int:
        return self._operation_count

    async def search(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ExternalSearchResult]:
        self._operation_count += 1
        normalized = _tokens(query)
        matches = [
            item
            for item in self._sources
            if any(normalized & _tokens(key) for key in item["query_keys"])
        ][:max_results]
        return [
            ExternalSearchResult(
                title=str(item["title"]),
                url=_source_url(str(item["source_id"])),
                domain="fixture.invalid",
                snippet=str(item["display_name"]),
            )
            for item in matches
        ]

    async def read(self, url: str) -> ExternalDocument:
        self._operation_count += 1
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "fixture.invalid":
            raise ValueError("合成外部资料后端拒绝非夹具 URL。")
        try:
            source = self._by_url[url]
        except KeyError as error:
            raise KeyError("合成外部资料不存在。") from error
        document_path = (self._root / source["document_path"]).resolve(strict=True)
        payload = json.loads(document_path.read_text(encoding="utf-8"))
        return ExternalDocument(
            url=url,
            final_url=url,
            title=str(payload["title"]),
            content=str(payload["content"]),
        )


def _validate_source(root: Path, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("合成外部资料条目必须是对象。")
    required = {
        "source_id",
        "query_keys",
        "title",
        "display_name",
        "document_path",
    }
    if not required <= value.keys():
        raise ValueError("合成外部资料条目缺少必需字段。")
    query_keys = value["query_keys"]
    if not isinstance(query_keys, list) or not all(
        isinstance(item, str) and item for item in query_keys
    ):
        raise ValueError("合成外部资料 query_keys 必须是非空字符串数组。")
    document_path = (root / str(value["document_path"])).resolve(strict=True)
    if not document_path.is_relative_to(root) or not document_path.is_file():
        raise ValueError("合成外部资料文档必须位于密封目录内。")
    return dict(value)


def _source_url(source_id: str) -> str:
    return f"{_FIXTURE_ORIGIN}/{source_id}"


def _tokens(value: str) -> frozenset[str]:
    """对中文夹具查询做确定性关键词切分，不引入分词器或网络搜索。"""
    separators = " \t\r\n，。；：、？！,.!?;:"
    normalized = value.casefold()
    for separator in separators:
        normalized = normalized.replace(separator, " ")
    parts = {part for part in normalized.split() if part}
    for keyword in ("灯塔", "记忆", "民俗", "潮汐", "回廊", "归潮灯"):
        if keyword in normalized:
            parts.add(keyword)
    return frozenset(parts)
