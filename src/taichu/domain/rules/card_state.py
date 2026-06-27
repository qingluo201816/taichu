"""State machines for AI cards and pending facts."""

from taichu.domain.exceptions import InvalidStateTransitionError
from taichu.domain.models.ai_card import AIResultCardStatus
from taichu.domain.models.pending_fact import PendingFactStatus


_AI_CARD_TRANSITIONS: dict[
    AIResultCardStatus,
    frozenset[AIResultCardStatus],
] = {
    AIResultCardStatus.GENERATED: frozenset(
        {
            AIResultCardStatus.INSERTED,
            AIResultCardStatus.SAVED_TO_INBOX,
            AIResultCardStatus.CONVERTED_TO_PENDING_FACT,
            AIResultCardStatus.DISCARDED,
            AIResultCardStatus.RETRIED,
        }
    ),
    AIResultCardStatus.INSERTED: frozenset(),
    AIResultCardStatus.SAVED_TO_INBOX: frozenset(),
    AIResultCardStatus.CONVERTED_TO_PENDING_FACT: frozenset(),
    AIResultCardStatus.DISCARDED: frozenset(),
    AIResultCardStatus.RETRIED: frozenset(),
}

_PENDING_FACT_TRANSITIONS: dict[
    PendingFactStatus,
    frozenset[PendingFactStatus],
] = {
    PendingFactStatus.PENDING: frozenset(
        {
            PendingFactStatus.CONFIRMED,
            PendingFactStatus.EDITED_CONFIRMED,
            PendingFactStatus.IGNORED,
        }
    ),
    PendingFactStatus.CONFIRMED: frozenset(),
    PendingFactStatus.EDITED_CONFIRMED: frozenset(),
    PendingFactStatus.IGNORED: frozenset(),
}


def assert_ai_card_transition_allowed(
    current: AIResultCardStatus,
    target: AIResultCardStatus,
) -> None:
    """Raise if an AIResultCard transition is outside the contract."""
    if target == current:
        return
    if target not in _AI_CARD_TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"智能助手结果卡片状态不能从“{current.value}”变更为“{target.value}”"
        )


def assert_pending_fact_transition_allowed(
    current: PendingFactStatus,
    target: PendingFactStatus,
) -> None:
    """Raise if a PendingFact transition is outside the contract."""
    if target == current:
        return
    if target not in _PENDING_FACT_TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"待确认设定状态不能从“{current.value}”变更为“{target.value}”"
        )
