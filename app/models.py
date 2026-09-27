from datetime import datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


ContextScope = Literal["category", "merchant", "customer", "trigger"]
SendAs = Literal["vera", "merchant_on_behalf"]
FromRole = Literal["merchant", "customer"]
ReplyAction = Literal["send", "wait", "end"]


class ContextPushRequest(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class ContextAcceptedResponse(BaseModel):
    accepted: Literal[True]
    ack_id: str
    stored_at: str


class ContextStaleResponse(BaseModel):
    accepted: Literal[False]
    reason: Literal["stale_version"]
    current_version: int


class ContextErrorResponse(BaseModel):
    accepted: Literal[False]
    reason: str
    details: str


class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: SendAs
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[TickAction]


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int


class ReplySendResponse(BaseModel):
    action: Literal["send"]
    body: str
    cta: str
    rationale: str


class ReplyWaitResponse(BaseModel):
    action: Literal["wait"]
    wait_seconds: int
    rationale: str


class ReplyEndResponse(BaseModel):
    action: Literal["end"]
    rationale: str


ReplyResponse = Union[ReplySendResponse, ReplyWaitResponse, ReplyEndResponse]


class HealthzResponse(BaseModel):
    status: Literal["ok"]
    uptime_seconds: int
    contexts_loaded: dict[str, int]


class MetadataResponse(BaseModel):
    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str


class ContextRecord(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str
    stored_at: str


class ConversationTurn(BaseModel):
    from_role: str
    message: str
    received_at: Optional[str] = None
    turn_number: Optional[int] = None


class ConversationState(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    send_as: Optional[str] = None
    trigger_id: Optional[str] = None
    suppression_key: Optional[str] = None
    turns: list[ConversationTurn] = Field(default_factory=list)
    last_cta: Optional[str] = None
    last_send_as: Optional[str] = None
    first_outbound_at: Optional[datetime] = None
    last_human_reply_at: Optional[datetime] = None
    auto_reply_count: int = 0
    opted_out: bool = False
    ended: bool = False
    wait_until: Optional[datetime] = None
    observed_language: Optional[str] = None
