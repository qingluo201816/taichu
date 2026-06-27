"""Domain-level exceptions for product contracts."""


class DomainRuleError(ValueError):
    """Base class for domain contract violations."""


class InvalidStateTransitionError(DomainRuleError):
    """Raised when a card or fact status transition is not allowed."""


class FactScopeViolationError(DomainRuleError):
    """Raised when non-fact workspace data is used as fact_scope input."""


class SourceRefValidationError(DomainRuleError):
    """Raised when a SourceRef violates the v1 evidence contract."""
