"""Adapters from concrete LLM SDK objects to application contracts."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


class LangChainLLMAdapter:
    """Expose a LangChain chat model through the application LLM contract."""

    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat_model = chat_model

    async def complete(self, prompt: str) -> str:
        """Return text content for a prompt."""
        message = await self._chat_model.ainvoke(prompt)
        content = message.content
        if isinstance(content, str):
            return content
        return _stringify_content(content)


def _stringify_content(content: Any) -> str:
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)
