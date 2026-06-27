"""LLM contract used by application services and workflows."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMContract(Protocol):
    """Minimal async text generation capability."""

    async def complete(self, prompt: str) -> str:
        """Generate text for an application-level prompt."""
        ...
