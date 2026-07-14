"""无需业务密钥的 DuckDuckGo 搜索与安全网页读取实现。"""

from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import ipaddress
import socket
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

from taichu.application.external_research.models import (
    ExternalDocument,
    ExternalSearchResult,
)


class DuckDuckGoExternalResearchBackend:
    """通过公开 HTML 搜索入口提供真实外部来源能力。"""

    def __init__(self, *, timeout_seconds: float = 20) -> None:
        self._timeout_seconds = timeout_seconds
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            )
        }

    async def search(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ExternalSearchResult]:
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            headers=self._headers,
        ) as client:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
            )
            response.raise_for_status()
        parser = _DuckDuckGoParser()
        parser.feed(response.text)
        results: list[ExternalSearchResult] = []
        seen: set[str] = set()
        for title, raw_url, snippet in parser.results:
            url = _unwrap_duckduckgo_url(raw_url)
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            if url in seen:
                continue
            seen.add(url)
            results.append(
                ExternalSearchResult(
                    title=title or parsed.hostname,
                    url=url,
                    domain=parsed.hostname,
                    snippet=snippet,
                )
            )
            if len(results) >= max_results:
                break
        return results

    async def read(self, url: str) -> ExternalDocument:
        current_url = url
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            headers=self._headers,
            follow_redirects=False,
        ) as client:
            for _ in range(6):
                await _validate_public_url(current_url)
                response = await client.get(current_url)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ExternalSourceReadError("外部来源重定向缺少目标地址。")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    raise ExternalSourceReadError("第一版只读取 HTML 或纯文本来源。")
                parser = _ReadableTextParser()
                parser.feed(response.text)
                return ExternalDocument(
                    url=url,
                    final_url=str(response.url),
                    title=parser.title.strip(),
                    content=parser.text(),
                )
        raise ExternalSourceReadError("外部来源重定向次数过多。")


class ExternalSourceReadError(RuntimeError):
    """外部网页不满足安全读取要求。"""


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[tuple[str, str, str]] = []
        self._anchor_url = ""
        self._anchor_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._in_anchor = False
        self._in_snippet = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._in_anchor = True
            self._anchor_url = values.get("href") or ""
            self._anchor_parts = []
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._anchor_parts.append(data)
        if self._in_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_anchor:
            self._in_anchor = False
            self.results.append(
                (" ".join(self._anchor_parts).strip(), self._anchor_url, "")
            )
        if self._in_snippet:
            snippet = " ".join(self._snippet_parts).strip()
            if self.results and not self.results[-1][2]:
                title, url, _ = self.results[-1]
                self.results[-1] = (title, url, snippet)
            if tag in {"a", "div", "span"}:
                self._in_snippet = False


class _ReadableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._ignored_depth = 0
        self._parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if not self._ignored_depth:
            text = " ".join(data.split())
            if text:
                self._parts.append(text)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line)


def _unwrap_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


async def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ExternalSourceReadError("外部来源只允许公开 HTTP 或 HTTPS 地址。")
    if parsed.username or parsed.password:
        raise ExternalSourceReadError("外部来源地址不能包含认证信息。")
    addresses = await asyncio.to_thread(_resolve_addresses, parsed.hostname)
    if not addresses:
        raise ExternalSourceReadError("外部来源域名无法解析。")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ExternalSourceReadError("外部来源不能指向本机或私有网络。")


def _resolve_addresses(hostname: str) -> set[str]:
    return {
        str(item[4][0])
        for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    }
