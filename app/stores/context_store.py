from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional

from app.models import ContextRecord

VALID_SCOPES = ("category", "merchant", "customer", "trigger")


class InvalidScopeError(ValueError):
    def __init__(self, scope: str) -> None:
        self.scope = scope
        super().__init__(f"invalid_scope: {scope}")


@dataclass
class PutResult:
    accepted: bool
    ack_id: str = ""
    stored_at: str = ""
    reason: Optional[str] = None
    current_version: Optional[int] = None
    noop: bool = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ContextStore:
    """Versioned in-memory store keyed by (scope, context_id)."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[tuple[str, str], ContextRecord] = {}

    def put(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
        delivered_at: str,
    ) -> PutResult:
        if scope not in VALID_SCOPES:
            raise InvalidScopeError(scope)

        key = (scope, context_id)
        ack_id = f"ack_{context_id}_v{version}"

        with self._lock:
            current = self._records.get(key)
            if current is None:
                stored_at = _utc_now_iso()
                self._records[key] = ContextRecord(
                    scope=scope,
                    context_id=context_id,
                    version=version,
                    payload=payload,
                    delivered_at=delivered_at,
                    stored_at=stored_at,
                )
                return PutResult(accepted=True, ack_id=ack_id, stored_at=stored_at)

            if version < current.version:
                return PutResult(
                    accepted=False,
                    reason="stale_version",
                    current_version=current.version,
                )

            if version == current.version:
                return PutResult(
                    accepted=True,
                    ack_id=ack_id,
                    stored_at=current.stored_at,
                    noop=True,
                )

            stored_at = _utc_now_iso()
            self._records[key] = ContextRecord(
                scope=scope,
                context_id=context_id,
                version=version,
                payload=payload,
                delivered_at=delivered_at,
                stored_at=stored_at,
            )
            return PutResult(accepted=True, ack_id=ack_id, stored_at=stored_at)

    def get(self, scope: str, context_id: Optional[str]) -> Optional[ContextRecord]:
        if not context_id:
            return None
        with self._lock:
            record = self._records.get((scope, context_id))
            return record.model_copy(deep=True) if record else None

    def counts(self) -> dict[str, int]:
        with self._lock:
            counts = {scope: 0 for scope in VALID_SCOPES}
            for scope, _context_id in self._records:
                counts[scope] = counts.get(scope, 0) + 1
            return counts
