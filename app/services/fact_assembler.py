from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.models import ContextRecord
from app.stores.context_store import ContextStore


class FactAssembler:
    """Join category + merchant + trigger + optional customer into a fact pack."""

    def __init__(self, context_store: ContextStore) -> None:
        self._contexts = context_store

    def assemble(
        self,
        trigger: ContextRecord,
        now: datetime,
    ) -> Optional[dict[str, Any]]:
        payload = trigger.payload
        merchant_id = payload.get("merchant_id")
        merchant = self._contexts.get("merchant", merchant_id)
        if merchant is None:
            return None

        category_slug = merchant.payload.get("category_slug")
        category = self._contexts.get("category", category_slug)
        if category is None:
            return None

        customer_id = payload.get("customer_id")
        customer: Optional[ContextRecord] = None
        if payload.get("scope") == "customer" or customer_id:
            customer = self._contexts.get("customer", customer_id)
            if customer is None:
                return None

        aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        return {
            "now": aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "trigger_id": trigger.context_id,
            "trigger": payload,
            "merchant": merchant.payload,
            "category": category.payload,
            "customer": customer.payload if customer else None,
        }
