"""MongoDB-backed structured knowledge infrastructure."""

from taichu.infrastructure.knowledge.mongo_repository import (
    MongoKnowledgeRepository,
)
from taichu.infrastructure.knowledge.sedimentation_progress_repository import (
    MongoKnowledgeSedimentationProgressRepository,
)

__all__ = ["MongoKnowledgeRepository", "MongoKnowledgeSedimentationProgressRepository"]
