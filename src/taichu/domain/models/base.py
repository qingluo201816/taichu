"""Shared helpers for immutable domain data contracts."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base model for Phase 0 data contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")
