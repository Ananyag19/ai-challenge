from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.models import (
    ContextPushRequest,
    HealthzResponse,
    MetadataResponse,
    ReplyRequest,
    TickRequest,
    TickResponse,
)
from app.services.action_emitter import ActionEmitter
from app.services.composer import Composer
from app.services.fact_assembler import FactAssembler
from app.services.policy_router import PolicyRouter, observe_language
from app.services.tick_planner import TickPlanner
from app.services.validator import Validator
from app.stores.context_store import ContextStore, InvalidScopeError
from app.stores.conversation_store import ConversationStore
from app.stores.suppression_store import SuppressionIndex


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="magicpin AI Challenge Bot", version=settings.bot_version)
    app.state.settings = settings
    app.state.start_time = time.time()
    app.state.context_store = ContextStore()
    app.state.conversation_store = ConversationStore()
    app.state.suppression = SuppressionIndex()
    app.state.composer = Composer()
    app.state.assembler = FactAssembler(app.state.context_store)
    app.state.validator = Validator(app.state.suppression)
    app.state.emitter = ActionEmitter(app.state.conversation_store, app.state.suppression)
    app.state.planner = TickPlanner(
        contexts=app.state.context_store,
        conversations=app.state.conversation_store,
        suppression=app.state.suppression,
        assembler=app.state.assembler,
        composer=app.state.composer,
        validator=app.state.validator,
        emitter=app.state.emitter,
    )
    app.state.policy = PolicyRouter(
        settings=settings,
        conversations=app.state.conversation_store,
        suppression=app.state.suppression,
        composer=app.state.composer,
    )
    _register_routes(app)
    return app


def _register_routes(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        if request.url.path == "/v1/context":
            return JSONResponse(
                status_code=400,
                content={
                    "accepted": False,
                    "reason": "malformed",
                    "details": str(exc.errors()),
                },
            )
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.get("/v1/healthz", response_model=HealthzResponse)
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime_seconds": int(time.time() - app.state.start_time),
            "contexts_loaded": app.state.context_store.counts(),
        }

    @app.get("/v1/metadata", response_model=MetadataResponse)
    async def metadata() -> dict[str, Any]:
        settings: Settings = app.state.settings
        return {
            "team_name": settings.team_name,
            "team_members": settings.team_members_list(),
            "model": settings.bot_model,
            "approach": settings.bot_approach,
            "contact_email": settings.contact_email,
            "version": settings.bot_version,
            "submitted_at": settings.submitted_at,
        }

    @app.post("/v1/context")
    async def push_context(body: ContextPushRequest) -> JSONResponse:
        try:
            result = app.state.context_store.put(
                scope=body.scope,
                context_id=body.context_id,
                version=body.version,
                payload=body.payload,
                delivered_at=body.delivered_at,
            )
        except InvalidScopeError as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "accepted": False,
                    "reason": "invalid_scope",
                    "details": str(exc),
                },
            )

        if not result.accepted:
            return JSONResponse(
                status_code=409,
                content={
                    "accepted": False,
                    "reason": result.reason or "stale_version",
                    "current_version": result.current_version,
                },
            )

        return JSONResponse(
            status_code=200,
            content={
                "accepted": True,
                "ack_id": result.ack_id,
                "stored_at": result.stored_at,
            },
        )

    @app.post("/v1/tick", response_model=TickResponse)
    async def tick(body: TickRequest) -> dict[str, Any]:
        actions = app.state.planner.plan(body.now, body.available_triggers)
        return {"actions": [action.model_dump() for action in actions]}

    @app.post("/v1/reply")
    async def reply(body: ReplyRequest) -> dict[str, Any]:
        conversations: ConversationStore = app.state.conversation_store
        suppression: SuppressionIndex = app.state.suppression
        policy: PolicyRouter = app.state.policy

        state = conversations.get_or_create(
            body.conversation_id,
            merchant_id=body.merchant_id,
            customer_id=body.customer_id,
        )
        language = observe_language(body.message)
        state = conversations.append_inbound(
            state,
            from_role=body.from_role,
            message=body.message,
            received_at=body.received_at,
            turn_number=body.turn_number,
            observed_language=language,
        )
        decision = policy.route_reply(state, body.message, body.received_at)

        if decision.auto_reply:
            state.auto_reply_count += 1
        if decision.opted_out:
            state.opted_out = True
            suppression.mark_merchant_opted_out(state.merchant_id)
        if decision.ended:
            state.ended = True
            suppression.mark_ended(state.conversation_id)
        if decision.wait_until is not None:
            state.wait_until = decision.wait_until

        conversations.save(state)
        return decision.response.model_dump()


app = create_app()
