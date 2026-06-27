"""State-machine contract tests."""

import unittest

from taichu.domain.exceptions import InvalidStateTransitionError
from taichu.domain.models import AIResultCardStatus, PendingFactStatus
from taichu.domain.rules import (
    assert_ai_card_transition_allowed,
    assert_pending_fact_transition_allowed,
)


class StateMachineContractTest(unittest.TestCase):
    """Verify Phase 0 status machines reject illegal transitions."""

    def test_ai_card_generated_can_move_to_inserted(self) -> None:
        assert_ai_card_transition_allowed(
            AIResultCardStatus.GENERATED,
            AIResultCardStatus.INSERTED,
        )

    def test_ai_card_terminal_transition_fails(self) -> None:
        with self.assertRaises(InvalidStateTransitionError):
            assert_ai_card_transition_allowed(
                AIResultCardStatus.INSERTED,
                AIResultCardStatus.SAVED_TO_INBOX,
            )

    def test_pending_fact_can_be_confirmed_from_pending(self) -> None:
        assert_pending_fact_transition_allowed(
            PendingFactStatus.PENDING,
            PendingFactStatus.CONFIRMED,
        )

    def test_confirmed_pending_fact_cannot_be_ignored(self) -> None:
        with self.assertRaises(InvalidStateTransitionError):
            assert_pending_fact_transition_allowed(
                PendingFactStatus.CONFIRMED,
                PendingFactStatus.IGNORED,
            )
