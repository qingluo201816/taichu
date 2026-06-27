"""Generated projection rebuild contract."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class IndexerContract(Protocol):
    """Rebuild generated indexes from source assets."""

    async def rebuild(self) -> None:
        """Recreate generated projections from source data."""
        ...
