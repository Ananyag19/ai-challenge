import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        team_name="Test Team",
        team_members="Ada,Bob",
        bot_model="none",
        bot_approach="foundation tests",
        contact_email="test@example.com",
        bot_version="0.1.0-test",
        submitted_at="2026-04-26T08:00:00Z",
        default_wait_seconds=1800,
        auto_reply_end_after=3,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def push_context(
    client: TestClient,
    scope: str,
    context_id: str,
    version: int,
    payload: dict,
    delivered_at: str = "2026-04-26T10:00:00Z",
):
    return client.post(
        "/v1/context",
        json={
            "scope": scope,
            "context_id": context_id,
            "version": version,
            "payload": payload,
            "delivered_at": delivered_at,
        },
    )
