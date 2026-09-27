from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import Settings
from app.models import (
    ConversationState,
    ReplyEndResponse,
    ReplyResponse,
    ReplySendResponse,
    ReplyWaitResponse,
)
from app.stores.conversation_store import ConversationStore, parse_iso
from app.stores.suppression_store import SuppressionIndex

STOP_PATTERNS = (
    re.compile(r"\bstop (messaging|sending|texting)\b", re.I),
    re.compile(r"\bnot interested\b", re.I),
    re.compile(r"\bunsubscribe\b", re.I),
    re.compile(r"\bdon't (message|contact) me\b", re.I),
    re.compile(r"\bdo not (message|contact) me\b", re.I),
    re.compile(r"\buseless spam\b", re.I),
    re.compile(r"\bstop sending these\b", re.I),
)

AUTO_REPLY_PATTERNS = (
    re.compile(r"thank you for contacting", re.I),
    re.compile(r"our team will (respond|get back)", re.I),
    re.compile(r"automated assistant", re.I),
    re.compile(r"this is an auto[- ]?reply", re.I),
    re.compile(r"we will get back to you", re.I),
)

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
HI_LATIN = {"haan", "nahi", "shukriya", "namaste", "kya", "aap", "ji", "theek"}


def observe_language(text: str) -> str:
    if DEVANAGARI.search(text):
        return "hi"
    tokens = set(re.findall(r"[a-zA-Z']+", text.lower()))
    if tokens & HI_LATIN:
        return "hi-en mix"
    return "en"


def looks_like_auto_reply(message: str) -> bool:
    return any(pattern.search(message) for pattern in AUTO_REPLY_PATTERNS)


def looks_like_opt_out(message: str) -> bool:
    return any(pattern.search(message) for pattern in STOP_PATTERNS)


@dataclass
class PolicyDecision:
    response: ReplyResponse
    opted_out: bool = False
    ended: bool = False
    wait_until: Optional[datetime] = None
    auto_reply: bool = False


class PolicyRouter:
    """Deterministic reply policy. Composition is not handled here."""

    def __init__(
        self,
        settings: Settings,
        conversations: ConversationStore,
        suppression: SuppressionIndex,
        composer: Any = None,
    ) -> None:
        self._settings = settings
        self._conversations = conversations
        self._suppression = suppression
        self._composer = composer

    def route_reply(
        self,
        state: ConversationState,
        message: str,
        received_at: str,
    ) -> PolicyDecision:
        received = parse_iso(received_at) or datetime.now(timezone.utc)

        if state.ended or state.opted_out or self._suppression.is_ended(state.conversation_id):
            return PolicyDecision(
                response=ReplyEndResponse(
                    action="end",
                    rationale="Conversation already closed; not sending further messages.",
                ),
                ended=True,
                opted_out=state.opted_out,
            )

        if looks_like_opt_out(message):
            return PolicyDecision(
                response=ReplyEndResponse(
                    action="end",
                    rationale="Merchant opted out or asked to stop; closing the conversation.",
                ),
                ended=True,
                opted_out=True,
            )

        last_inbound = None
        for turn in reversed(state.turns[:-1]):
            if turn.from_role in {"merchant", "customer"}:
                last_inbound = turn.message
                break
        repeated = last_inbound is not None and last_inbound.strip() == message.strip()
        auto_reply = looks_like_auto_reply(message) or repeated

        if auto_reply:
            count = state.auto_reply_count + 1
            if count >= self._settings.auto_reply_end_after:
                return PolicyDecision(
                    response=ReplyEndResponse(
                        action="end",
                        rationale="Repeated auto-reply detected; exiting without further nudges.",
                    ),
                    ended=True,
                    auto_reply=True,
                )
            wait_seconds = self._settings.default_wait_seconds
            return PolicyDecision(
                response=ReplyWaitResponse(
                    action="wait",
                    wait_seconds=wait_seconds,
                    rationale="Detected canned auto-reply; backing off before retrying.",
                ),
                wait_until=received + timedelta(seconds=wait_seconds),
                auto_reply=True,
            )

        # Call composer for the actual reply
        draft = self._composer.compose_reply(state.model_dump(), message)
        if draft is None:
            wait_seconds = self._settings.default_wait_seconds
            return PolicyDecision(
                response=ReplyWaitResponse(
                    action="wait",
                    wait_seconds=wait_seconds,
                    rationale="Composer returned None; falling back to wait.",
                ),
                wait_until=received + timedelta(seconds=wait_seconds),
            )

        action = draft.get("action", "send")
        if action == "end":
            return PolicyDecision(
                response=ReplyEndResponse(
                    action="end",
                    rationale=draft.get("rationale", "Graceful exit"),
                ),
                ended=True,
            )
        elif action == "wait":
            wait_seconds = draft.get("wait_seconds", self._settings.default_wait_seconds)
            return PolicyDecision(
                response=ReplyWaitResponse(
                    action="wait",
                    wait_seconds=wait_seconds,
                    rationale=draft.get("rationale", "Waiting"),
                ),
                wait_until=received + timedelta(seconds=wait_seconds),
            )
        else:
            return PolicyDecision(
                response=ReplySendResponse(
                    action="send",
                    body=draft.get("body", ""),
                    cta=draft.get("cta", "none"),
                    rationale=draft.get("rationale", ""),
                )
            )
