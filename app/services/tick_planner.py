from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.models import TickAction
from app.services.action_emitter import ActionEmitter
from app.services.composer import Composer
from app.services.fact_assembler import FactAssembler
from app.services.validator import Validator
from app.stores.context_store import ContextStore
from app.stores.conversation_store import ConversationStore, parse_iso
from app.stores.suppression_store import SuppressionIndex

MAX_ACTIONS_PER_TICK = 20


class TickPlanner:
    """Select eligible triggers and (later) emit outbound actions."""

    def __init__(
        self,
        contexts: ContextStore,
        conversations: ConversationStore,
        suppression: SuppressionIndex,
        assembler: FactAssembler,
        composer: Composer,
        validator: Validator,
        emitter: ActionEmitter,
    ) -> None:
        self._contexts = contexts
        self._conversations = conversations
        self._suppression = suppression
        self._assembler = assembler
        self._composer = composer
        self._validator = validator
        self._emitter = emitter

    def plan(self, now: str, available_triggers: list[str]) -> list[TickAction]:
        current = parse_iso(now) or datetime.now(timezone.utc)
        actions: list[TickAction] = []
        seen_pairs: set[tuple[str, str]] = set()

        for trigger_id in available_triggers:
            if len(actions) >= MAX_ACTIONS_PER_TICK:
                break

            trigger = self._contexts.get("trigger", trigger_id)
            if trigger is None:
                continue

            payload = trigger.payload
            if self._is_expired(payload.get("expires_at"), current):
                continue

            suppression_key = payload.get("suppression_key")
            if self._suppression.is_used(suppression_key):
                continue

            merchant_id = payload.get("merchant_id")
            if not merchant_id:
                continue
            if self._suppression.is_merchant_opted_out(merchant_id):
                continue
            if self._conversations.has_open_for_merchant(merchant_id):
                continue

            facts = self._assembler.assemble(trigger, current)
            if facts is None:
                continue

            draft = self._composer.compose_outbound(facts)
            if draft is None:
                continue

            emitted = self._emitter.emit(draft)
            if emitted is None:
                continue

            pair = (emitted.merchant_id, emitted.conversation_id)
            if pair in seen_pairs:
                continue
            validated = self._validator.validate_action(emitted)
            if validated is None:
                continue

            self._emitter.record(validated)
            seen_pairs.add(pair)
            actions.append(validated)

        return actions

    @staticmethod
    def _is_expired(expires_at: Optional[str], now: datetime) -> bool:
        expiry = parse_iso(expires_at)
        if expiry is None:
            return False
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        comparable = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        return expiry <= comparable
