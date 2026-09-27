from __future__ import annotations

from typing import Any, Optional

from app.models import TickAction
from app.stores.conversation_store import ConversationStore
from app.stores.suppression_store import SuppressionIndex


class ActionEmitter:
    """Turn a composer dict into a TickAction and record suppression/conversation."""

    def __init__(
        self,
        conversations: ConversationStore,
        suppression: SuppressionIndex,
    ) -> None:
        self._conversations = conversations
        self._suppression = suppression

    def emit(self, draft: dict[str, Any]) -> Optional[TickAction]:
        try:
            action = TickAction.model_validate(draft)
        except Exception:
            return None
        return action

    def record(self, action: TickAction) -> None:
        self._suppression.mark_used(action.suppression_key)
        self._suppression.remember_body(action.conversation_id, action.body)
        state = self._conversations.get_or_create(
            action.conversation_id,
            merchant_id=action.merchant_id,
            customer_id=action.customer_id,
        )
        state.send_as = action.send_as
        state.last_send_as = action.send_as
        state.trigger_id = action.trigger_id
        state.suppression_key = action.suppression_key
        state.last_cta = action.cta
        self._conversations.save(state)
