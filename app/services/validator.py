from __future__ import annotations

from typing import Optional

from app.models import TickAction
from app.stores.suppression_store import SuppressionIndex


class Validator:
    """Post-composition checks. Foundation step: structural + anti-repeat only."""

    def __init__(self, suppression: SuppressionIndex) -> None:
        self._suppression = suppression

    def validate_action(self, action: TickAction) -> Optional[TickAction]:
        if not action.body.strip():
            return None
        if "http://" in action.body.lower() or "https://" in action.body.lower():
            return None
        if self._suppression.already_sent(action.conversation_id, action.body):
            return None
        return action
