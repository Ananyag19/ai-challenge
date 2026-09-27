from __future__ import annotations

from threading import Lock
from typing import Optional


class SuppressionIndex:
    def __init__(self) -> None:
        self._lock = Lock()
        self._used_keys: set[str] = set()
        self._opted_out_merchants: set[str] = set()
        self._ended_conversations: set[str] = set()
        self._sent_bodies: dict[str, set[str]] = {}

    def mark_used(self, suppression_key: Optional[str]) -> None:
        if not suppression_key:
            return
        with self._lock:
            self._used_keys.add(suppression_key)

    def is_used(self, suppression_key: Optional[str]) -> bool:
        if not suppression_key:
            return False
        with self._lock:
            return suppression_key in self._used_keys

    def mark_merchant_opted_out(self, merchant_id: Optional[str]) -> None:
        if not merchant_id:
            return
        with self._lock:
            self._opted_out_merchants.add(merchant_id)

    def is_merchant_opted_out(self, merchant_id: Optional[str]) -> bool:
        if not merchant_id:
            return False
        with self._lock:
            return merchant_id in self._opted_out_merchants

    def mark_ended(self, conversation_id: str) -> None:
        with self._lock:
            self._ended_conversations.add(conversation_id)

    def is_ended(self, conversation_id: str) -> bool:
        with self._lock:
            return conversation_id in self._ended_conversations

    def remember_body(self, conversation_id: str, body: str) -> None:
        with self._lock:
            self._sent_bodies.setdefault(conversation_id, set()).add(body)

    def already_sent(self, conversation_id: str, body: str) -> bool:
        with self._lock:
            return body in self._sent_bodies.get(conversation_id, set())
