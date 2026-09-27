from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from app.models import ConversationState, ConversationTurn


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class ConversationStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._conversations: dict[str, ConversationState] = {}

    def get(self, conversation_id: str) -> Optional[ConversationState]:
        with self._lock:
            record = self._conversations.get(conversation_id)
            return record.model_copy(deep=True) if record else None

    def upsert(self, state: ConversationState) -> ConversationState:
        with self._lock:
            self._conversations[state.conversation_id] = state
            return state.model_copy(deep=True)

    def get_or_create(
        self,
        conversation_id: str,
        merchant_id: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> ConversationState:
        with self._lock:
            existing = self._conversations.get(conversation_id)
            if existing is not None:
                updated = existing.model_copy(deep=True)
                if merchant_id and not updated.merchant_id:
                    updated.merchant_id = merchant_id
                if customer_id and not updated.customer_id:
                    updated.customer_id = customer_id
                self._conversations[conversation_id] = updated
                return updated.model_copy(deep=True)

            created = ConversationState(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
            )
            self._conversations[conversation_id] = created
            return created.model_copy(deep=True)

    def save(self, state: ConversationState) -> ConversationState:
        with self._lock:
            self._conversations[state.conversation_id] = state
            return state.model_copy(deep=True)

    def has_open_for_merchant(self, merchant_id: Optional[str]) -> bool:
        if not merchant_id:
            return False
        with self._lock:
            for state in self._conversations.values():
                if state.merchant_id == merchant_id and not state.ended and not state.opted_out:
                    return True
            return False

    def append_inbound(
        self,
        state: ConversationState,
        from_role: str,
        message: str,
        received_at: str,
        turn_number: int,
        observed_language: Optional[str],
    ) -> ConversationState:
        state.turns.append(
            ConversationTurn(
                from_role=from_role,
                message=message,
                received_at=received_at,
                turn_number=turn_number,
            )
        )
        parsed = parse_iso(received_at)
        state.last_human_reply_at = parsed or datetime.now(timezone.utc)
        if observed_language:
            state.observed_language = observed_language
        return self.save(state)
