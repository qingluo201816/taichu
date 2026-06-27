"""Domain rules for Phase 0 contracts."""

from taichu.domain.rules.card_state import (
    assert_ai_card_transition_allowed,
    assert_pending_fact_transition_allowed,
)
from taichu.domain.rules.fact_scope import (
    FactScopeSource,
    RetrievalScopeName,
    assert_allowed_in_fact_scope,
    is_allowed_in_fact_scope,
    resolve_retrieval_scope,
)
from taichu.domain.rules.source_ref import (
    SourceRefValidationResult,
    SourceRefValidator,
    validate_source_ref_contract,
)

__all__ = [
    "assert_ai_card_transition_allowed",
    "assert_pending_fact_transition_allowed",
    "FactScopeSource",
    "RetrievalScopeName",
    "assert_allowed_in_fact_scope",
    "is_allowed_in_fact_scope",
    "resolve_retrieval_scope",
    "SourceRefValidationResult",
    "SourceRefValidator",
    "validate_source_ref_contract",
]
