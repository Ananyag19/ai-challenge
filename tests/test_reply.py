import json

import pytest

from app.services import composer as composer_module


def test_reply_with_clear_intent_sends_via_fallback(client, monkeypatch):
    # No GEMINI_API_KEY in the test environment -> falls back to the
    # deterministic composer, which must still detect explicit intent
    # ("Yes, ...") and move to action mode rather than parking on "wait"
    # (this is the intent-handoff failure the challenge brief calls out).
    monkeypatch.setattr(composer_module, "_get_api_key", lambda: "")
    response = client.post(
        "/v1/reply",
        json={
            "conversation_id": "conv_001",
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "customer_id": None,
            "from_role": "merchant",
            "message": "Yes, send me the abstract",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "send"
    assert body["body"]
    assert "rationale" in body


def test_reply_without_intent_signal_waits_via_fallback(client, monkeypatch):
    monkeypatch.setattr(composer_module, "_get_api_key", lambda: "")
    response = client.post(
        "/v1/reply",
        json={
            "conversation_id": "conv_002",
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "customer_id": None,
            "from_role": "merchant",
            "message": "What time does the clinic close today?",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "wait"
    assert body["wait_seconds"] == 1800
    assert "rationale" in body


def test_reply_uses_llm_composition_when_available(client, monkeypatch):
    llm_reply = json.dumps({
        "action": "send",
        "body": "Great, I'll get the setup started for you right away.",
        "cta": "none",
        "rationale": "Merchant signalled clear intent; moved straight to action mode.",
    })
    monkeypatch.setattr(composer_module, "_call_gemini", lambda prompt: llm_reply)

    response = client.post(
        "/v1/reply",
        json={
            "conversation_id": "conv_003",
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "customer_id": None,
            "from_role": "merchant",
            "message": "Yes let's do it",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "send"
    assert body["body"] == "Great, I'll get the setup started for you right away."
    assert body["cta"] == "none"


@pytest.mark.parametrize("message", [
    "yes",
    "yep",
    "yeah",
    "sure",
    "ok",
    "okay",
    "go ahead",
    "I'm in",
    "sounds good",
    "let's do it",
    "do it",
    "Ok lets do it. Whats next?",
])
@pytest.mark.parametrize("model_action", ["wait", "end"])
def test_reply_explicit_intent_overrides_non_send_llm_action(
    client, monkeypatch, message, model_action
):
    monkeypatch.setattr(
        composer_module,
        "_call_gemini",
        lambda prompt: json.dumps({"action": model_action, "rationale": "Model choice"}),
    )

    response = client.post(
        "/v1/reply",
        json={
            "conversation_id": f"intent_{message}_{model_action}",
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "customer_id": None,
            "from_role": "merchant",
            "message": message,
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "send"
    assert body["body"]


def test_reply_ends_on_opt_out(client):
    response = client.post(
        "/v1/reply",
        json={
            "conversation_id": "conv_hostile",
            "merchant_id": "m_001",
            "from_role": "merchant",
            "message": "Stop messaging me. This is useless spam.",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert response.status_code == 200
    assert response.json()["action"] == "end"

    again = client.post(
        "/v1/reply",
        json={
            "conversation_id": "conv_hostile",
            "merchant_id": "m_001",
            "from_role": "merchant",
            "message": "hello?",
            "received_at": "2026-04-26T11:00:00Z",
            "turn_number": 3,
        },
    )
    assert again.status_code == 200
    assert again.json()["action"] == "end"


def test_reply_detects_repeated_auto_reply_and_ends(client):
    payload = {
        "conversation_id": "conv_auto",
        "merchant_id": "m_001",
        "from_role": "merchant",
        "message": "Thank you for contacting us! Our team will respond shortly.",
        "received_at": "2026-04-26T10:45:00Z",
        "turn_number": 2,
    }
    first = client.post("/v1/reply", json=payload)
    assert first.status_code == 200
    assert first.json()["action"] == "wait"

    payload["turn_number"] = 3
    second = client.post("/v1/reply", json=payload)
    assert second.json()["action"] == "wait"

    payload["turn_number"] = 4
    third = client.post("/v1/reply", json=payload)
    assert third.status_code == 200
    assert third.json()["action"] == "end"
