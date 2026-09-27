from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger("vera.composer")

MAX_ATTEMPTS = 2  # 1 initial call + 1 retry on transient failure
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _get_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


def _get_model() -> str:
    return os.environ.get("LLM_MODEL", "gemini-2.5-flash")


def _call_gemini(prompt: str) -> str:
    """Call Gemini REST API once and return the raw text response.

    Raises on any failure; callers are responsible for retry/fallback.
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    model = _get_model()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=28)
    data = json.loads(resp.read().decode("utf-8"))
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_gemini_with_retry(prompt: str) -> str:
    """Call Gemini, retrying once on transient errors (timeouts, 5xx, connection resets).

    Does NOT retry on clearly permanent failures (missing key, 4xx other than 429)
    since retrying those just wastes the tick's time budget.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _call_gemini(prompt)
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 or e.code >= 500:
                logger.warning("Gemini HTTP %s on attempt %d/%d, retrying", e.code, attempt, MAX_ATTEMPTS)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_error = e
            logger.warning("Gemini network error on attempt %d/%d: %s", attempt, MAX_ATTEMPTS, e)
            continue
    assert last_error is not None
    raise last_error


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Parse the model's JSON output, tolerating stray markdown fences."""
    cleaned = FENCE_RE.sub("", raw.strip()).strip()
    return json.loads(cleaned)


OUTBOUND_PROMPT = """
You are Vera, a merchant AI assistant for magicpin. Compose an outbound WhatsApp message to a merchant or their customer using the contexts below.

RULES:
- Use only facts explicitly present in CONTEXTS. Never invent discounts, prices, offers, inventory, customers, capabilities, results, deadlines, or guarantees, and never claim an action is already completed.
- Build one concise message by connecting the trigger to the category and to a relevant fact about this merchant; the merchant's name alone is not personalization.
- Turn that connection into a sensible, concrete next action supported by the supplied facts. Explain why acting now matters only when the trigger and its dates or urgency support that reason.
- Use `now` as the temporal reference. If a relative countdown conflicts with an absolute date in the trigger, prefer the date and omit the countdown.
- Trigger relevance: say what event or change prompted this message.
- Category relevance: make clear why that event matters to this business type, following its voice and avoiding taboo vocabulary.
- Merchant relevance: use a relevant supplied signal, performance figure, active offer, locality, or conversation fact naturally; omit it if none supports the connection.
- Actionable business decision: recommend one practical next step that follows from the trigger and facts, without generic advice or implying it has been done.
- CTA/engagement: end with one specific, low-friction question that asks the merchant to approve or choose that next step. Do not add another ask.
- Specificity: prefer exact verifiable figures, dates, and citations already in context. Never use generic "X% off" framings.
- Language: use only a language preference explicitly present in context; otherwise use concise English.
- Keep the body concise and WhatsApp-natural. Do NOT re-introduce yourself after the first message.

Return ONLY valid JSON (no markdown fences):
{{
  "body": "<WhatsApp message text>",
  "cta": "open_ended" | "binary_choice" | "none",
  "send_as": "vera" | "merchant_on_behalf",
  "rationale": "<1-2 sentence explanation>"
}}

CONTEXTS:
{facts}
"""

REPLY_PROMPT = """
You are Vera, a merchant AI assistant for magicpin. A merchant has replied to your previous message.
Decide the next action.

RULES:
- If the merchant signals clear intent ("yes", "let's do it", "go ahead") -> switch to action mode immediately, do NOT ask qualifying questions again.
- If the merchant asks a question -> answer it concisely.
- If the merchant is hostile or opts out -> end gracefully.
- Do NOT repeat the same body verbatim as a previous message.

Return ONLY valid JSON (no markdown fences):
{{
  "action": "send" | "wait" | "end",
  "body": "<reply text, only if action is send>",
  "cta": "open_ended" | "none",
  "rationale": "<why this action>"
}}

CONVERSATION HISTORY:
{history}

MERCHANT'S LATEST MESSAGE:
{message}
"""

INTENT_RE = re.compile(
    r"\b(yes|yep|yeah|sure|ok(ay)?|let's do it|go ahead|i'?m in|sounds good|do it)\b",
    re.IGNORECASE,
)


def _fallback_outbound(facts: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, template-based outbound message used only when the LLM
    is unreachable. Not as sharp as the LLM copy, but keeps the bot emitting
    real actions instead of silently dropping the trigger.
    """
    merchant = facts.get("merchant", {}) or {}
    trigger = facts.get("trigger", {}) or {}
    category = facts.get("category", {}) or {}
    customer = facts.get("customer")

    name = merchant.get("identity", {}).get("name", "there")
    kind = trigger.get("kind", "an update")
    offers = merchant.get("offers", []) or category.get("offer_catalog", []) or []
    offer_title = None
    for offer in offers:
        title = offer.get("title") if isinstance(offer, dict) else offer
        status = offer.get("status") if isinstance(offer, dict) else None
        if title and (status is None or status == "active"):
            offer_title = title
            break

    scope = trigger.get("scope", "merchant")
    send_as = "merchant_on_behalf" if (scope == "customer" or customer) else "vera"

    if customer:
        cust_name = customer.get("name", "there")
        body = (
            f"Hi {cust_name}, this is {name} here. "
            + (f"We have {offer_title} available. " if offer_title else "")
            + "Reply and we'll get you sorted."
        )
    else:
        body = (
            f"Hi {name}, quick note on {str(kind).replace('_', ' ')} for your account"
            + (f" - {offer_title} is live on your profile." if offer_title else ".")
            + " Want me to walk you through the next step?"
        )

    return {
        "conversation_id": f"conv_{merchant.get('merchant_id')}_{facts.get('trigger_id')}",
        "merchant_id": merchant.get("merchant_id"),
        "customer_id": customer.get("customer_id") if customer else None,
        "send_as": send_as,
        "trigger_id": facts.get("trigger_id"),
        "template_name": "vera_fallback_v1",
        "template_params": [name],
        "body": body,
        "cta": "open_ended",
        "suppression_key": trigger.get("suppression_key", ""),
        "rationale": "LLM unavailable; deterministic fallback template used.",
    }


def _fallback_reply(message: str) -> dict[str, Any]:
    """Deterministic reply decision used only when the LLM is unreachable."""
    if INTENT_RE.search(message or ""):
        return {
            "action": "send",
            "body": "Great - let's get that started. I'll share the next step in a moment.",
            "cta": "none",
            "rationale": "LLM unavailable; detected explicit intent, moved to action mode via fallback.",
        }
    return {
        "action": "wait",
        "cta": "none",
        "rationale": "LLM unavailable; deferring rather than guessing at a reply.",
    }


class Composer:
    """Outbound / reply composer backed by the Gemini API, with a deterministic
    fallback so a network/LLM outage degrades gracefully instead of silently
    dropping every action.
    """

    def compose_outbound(self, facts: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            prompt = OUTBOUND_PROMPT.format(facts=json.dumps(facts, indent=2))
            raw = _call_gemini_with_retry(prompt)
            result = _parse_json_response(raw)
        except Exception as e:
            logger.warning("compose_outbound: LLM call failed (%s: %s); using fallback", type(e).__name__, e)
            try:
                return _fallback_outbound(facts)
            except Exception as fallback_error:
                logger.error("compose_outbound: fallback also failed: %s", fallback_error)
                return None

        merchant = facts.get("merchant", {}) or {}
        customer = facts.get("customer")

        return {
            "conversation_id": f"conv_{merchant.get('merchant_id')}_{facts.get('trigger_id')}",
            "merchant_id": merchant.get("merchant_id"),
            "customer_id": customer.get("customer_id") if customer else None,
            "send_as": result.get("send_as", "vera"),
            "trigger_id": facts.get("trigger_id"),
            "template_name": "vera_generic_v1",
            "template_params": [merchant.get("identity", {}).get("name", "Merchant")],
            "body": result.get("body", ""),
            "cta": result.get("cta", "none"),
            "suppression_key": facts.get("trigger", {}).get("suppression_key", ""),
            "rationale": result.get("rationale", ""),
        }

    def compose_reply(
        self,
        facts: dict[str, Any],
        message: str,
    ) -> Optional[dict[str, Any]]:
        turns = facts.get("turns", [])
        history = "".join(
            f"[{t.get('from_role', 'unknown')}] {t.get('message', '')}\n"
            for t in turns
        )
        try:
            prompt = REPLY_PROMPT.format(history=history, message=message)
            raw = _call_gemini_with_retry(prompt)
            result = _parse_json_response(raw)
            if INTENT_RE.search(message or "") and result.get("action") != "send":
                logger.info("compose_reply: explicit intent overrides model action %r", result.get("action"))
                return _fallback_reply(message)
            return result
        except Exception as e:
            logger.warning("compose_reply: LLM call failed (%s: %s); using fallback", type(e).__name__, e)
            try:
                return _fallback_reply(message)
            except Exception as fallback_error:
                logger.error("compose_reply: fallback also failed: %s", fallback_error)
                return None
