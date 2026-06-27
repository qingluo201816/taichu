"""SourceRef validation interface and local contract checks."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from taichu.domain.exceptions import SourceRefValidationError
from taichu.domain.models.source_ref import SourceRef


@dataclass(frozen=True)
class SourceRefValidationResult:
    """Result returned by storage-aware SourceRef validators."""

    valid: bool
    ref: SourceRef
    message: str | None = None


@runtime_checkable
class SourceRefValidator(Protocol):
    """Storage-aware validator implemented outside the domain layer."""

    def validate(self, ref: SourceRef) -> SourceRefValidationResult:
        """Validate freshness and optionally return a relocated reference."""
        ...


def validate_source_ref_contract(ref: SourceRef) -> SourceRef:
    """Run local v1 checks already encoded by the SourceRef model."""
    try:
        return SourceRef.model_validate(ref.model_dump())
    except ValidationError as exc:
        raise SourceRefValidationError(str(exc)) from exc
