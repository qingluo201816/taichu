"""外部研究应用能力。"""

from taichu.application.external_research.models import (
    ExternalDocument,
    ExternalSearchResult,
)
from taichu.application.external_research.service import ExternalResearchService

__all__ = [
    "ExternalDocument",
    "ExternalResearchService",
    "ExternalSearchResult",
]
