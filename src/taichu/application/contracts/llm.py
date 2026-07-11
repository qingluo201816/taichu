"""LLM contracts used by application services and workflows."""

from __future__ import annotations

from typing import Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, model_validator


class LLMModelIdentity(BaseModel):
    """Auditable identity reported by the runtime that created an LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = ""
    model_id: str = ""
    family: str = ""
    endpoint_kind: str = ""
    fingerprint: str | None = None
    known: bool = False
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        """Keep known and unknown identities explicit and reviewable."""
        if self.known:
            if not self.provider.strip() or not self.model_id.strip():
                raise ValueError("已知模型身份必须包含供应商和模型标识。")
            if self.unknown_reason is not None:
                raise ValueError("已知模型身份不能包含未知原因。")
        elif not (self.unknown_reason or "").strip():
            raise ValueError("未知模型身份必须说明原因。")
        return self

    @classmethod
    def unknown(
        cls,
        reason: str,
        *,
        provider: str = "",
        model_id: str = "",
        family: str = "",
        endpoint_kind: str = "",
    ) -> LLMModelIdentity:
        """Create an identity that must not be treated as independent evidence."""
        return cls(
            provider=provider,
            model_id=model_id,
            family=family,
            endpoint_kind=endpoint_kind,
            known=False,
            unknown_reason=reason,
        )


@runtime_checkable
class LLMContract(Protocol):
    """Minimal async text generation capability."""

    @property
    def model_identity(self) -> LLMModelIdentity:
        """Return the identity supplied by the actual runtime adapter."""
        ...

    async def complete(self, prompt: str) -> str:
        """Generate text for an application-level prompt."""
        ...
