"""安全探测 Right Code 模型名称、协议、流式与 usage 支持。"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv

from taichu.config import Settings
from taichu.infrastructure.llm.catalog import LLMModelCatalog


async def main() -> int:
    """只从本机环境读取密钥，输出不包含请求正文和上游响应。"""
    load_dotenv()
    settings = Settings()
    token = os.getenv("RIGHTCODE_API_KEY", "").strip()
    if not token:
        print("未执行：缺少本地安全密钥 RIGHTCODE_API_KEY。")
        return 2

    timeout = httpx.Timeout(settings.rightcode_request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        results = []
        for profile in LLMModelCatalog(settings).list_models():
            result = await _probe_responses(client, settings, token, profile)
            if not result["请求是否成功"] and (
                profile.id.startswith("claude-")
                or profile.id.startswith("deepseek-")
            ):
                result = await _probe_anthropic_messages(
                    client, settings, token, profile, result
                )
            results.append(result)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["请求是否成功"] for item in results) else 1


async def _probe_responses(
    client: httpx.AsyncClient,
    settings: Settings,
    token: str,
    profile: Any,
) -> dict[str, Any]:
    endpoint = f"{settings.rightcode_responses_base_url.rstrip('/')}/responses"
    payload = {
        "model": profile.upstream_model,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "请只回复：可用"}],
            }
        ],
        "max_output_tokens": 8,
        "stream": True,
    }
    return await _send_stream_probe(
        client,
        endpoint=endpoint,
        headers=_headers(token, anthropic=False),
        payload=payload,
        profile=profile,
        protocol="openai_responses",
    )


async def _probe_anthropic_messages(
    client: httpx.AsyncClient,
    settings: Settings,
    token: str,
    profile: Any,
    responses_result: dict[str, Any],
) -> dict[str, Any]:
    base_url = (
        settings.rightcode_deepseek_anthropic_base_url
        if profile.id.startswith("deepseek-")
        else settings.rightcode_claude_sale_base_url
    )
    endpoint = f"{base_url.rstrip('/')}/v1/messages"
    payload = {
        "model": profile.upstream_model,
        "messages": [{"role": "user", "content": "请只回复：可用"}],
        "max_tokens": 1024 if profile.id.startswith("deepseek-") else 8,
        "stream": True,
    }
    result = await _send_stream_probe(
        client,
        endpoint=endpoint,
        headers=_headers(token, anthropic=True),
        payload=payload,
        profile=profile,
        protocol="anthropic_messages",
    )
    result["Responses 探测状态码"] = responses_result["错误状态码"]
    if not result["请求是否成功"]:
        result["脱敏错误摘要"] = (
            f"Responses：{responses_result['脱敏错误摘要']}；"
            f"Messages：{result['脱敏错误摘要']}"
        )
    return result


async def _send_stream_probe(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    profile: Any,
    protocol: str,
) -> dict[str, Any]:
    status_code: int | None = None
    usage_returned = False
    text_returned = False
    success = False
    error_summary = ""
    try:
        async with client.stream(
            "POST", endpoint, headers=headers, json=payload
        ) as response:
            status_code = response.status_code
            request_succeeded = response.status_code < 400
            if request_succeeded:
                async for line in response.aiter_lines():
                    if line.startswith("data:") and "usage" in line:
                        usage_returned = True
                    if line.startswith("data:") and (
                        "output_text.delta" in line or "text_delta" in line
                    ):
                        text_returned = True
                success = text_returned
                if not text_returned:
                    error_summary = "模型未返回正文"
            else:
                error_summary = _status_summary(response.status_code)
    except httpx.TimeoutException:
        error_summary = "请求超时"
    except httpx.NetworkError:
        error_summary = "网络连接失败"
    except Exception:
        error_summary = "响应解析失败"
    return {
        "模型内部 ID": profile.id,
        "显示名称": profile.display_name,
        "上游模型名": profile.upstream_model,
        "使用端点": endpoint,
        "使用协议": protocol,
        "请求是否成功": success,
        "是否支持流式": success,
        "是否返回正文": text_returned,
        "是否返回 usage": usage_returned,
        "错误状态码": status_code if status_code and status_code >= 400 else None,
        "脱敏错误摘要": error_summary or None,
    }


def _headers(token: str, *, anthropic: bool) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if anthropic:
        headers.update({"x-api-key": token, "anthropic-version": "2023-06-01"})
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _status_summary(status_code: int) -> str:
    if status_code in {401, 403}:
        return "密钥或模型权限不足"
    if status_code == 429:
        return "请求受限或额度不足"
    if status_code >= 500:
        return "上游服务异常"
    return "请求被上游拒绝"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
