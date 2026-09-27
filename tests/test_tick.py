import json

from tests.conftest import push_context
from app.services import composer as composer_module


def _seed_valid_trigger(client) -> None:
    assert push_context(client, "category", "dentists", 1, {"slug": "dentists"}).status_code == 200
    assert push_context(
        client,
        "merchant",
        "m_001_drmeera_dentist_delhi",
        1,
        {
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "category_slug": "dentists",
            "identity": {"name": "Dr. Meera's Dental Clinic"},
        },
    ).status_code == 200
    assert push_context(
        client,
        "trigger",
        "trg_001_research_digest_dentists",
        1,
        {
            "id": "trg_001_research_digest_dentists",
            "scope": "merchant",
            "kind": "research_digest",
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "customer_id": None,
            "suppression_key": "research:dentists:2026-W17",
            "expires_at": "2026-05-03T00:00:00Z",
        },
    ).status_code == 200


def test_tick_uses_deterministic_fallback_when_llm_unavailable(client):
    # No GEMINI_API_KEY is configured in the test environment, so the composer
    # should fall back to its deterministic template rather than returning
    # nothing for a perfectly valid, non-expired trigger.
    _seed_valid_trigger(client)
    response = client.post(
        "/v1/tick",
        json={
            "now": "2026-04-26T10:35:00Z",
            "available_triggers": ["trg_001_research_digest_dentists"],
        },
    )
    assert response.status_code == 200
    actions = response.json()["actions"]
    assert len(actions) == 1
    action = actions[0]
    assert action["merchant_id"] == "m_001_drmeera_dentist_delhi"
    assert action["trigger_id"] == "trg_001_research_digest_dentists"
    assert action["body"]  # non-empty fallback body was generated
    assert action["template_name"] == "vera_fallback_v1"


def test_tick_uses_llm_composition_when_available(client, monkeypatch):
    _seed_valid_trigger(client)

    llm_reply = json.dumps({
        "body": "Dr. Meera, JIDA's Oct issue landed with a fluoride recall finding relevant to your patients. Want the abstract?",
        "cta": "open_ended",
        "send_as": "vera",
        "rationale": "Research digest relevance + curiosity CTA.",
    })
    monkeypatch.setattr(composer_module, "_call_gemini", lambda prompt: llm_reply)

    response = client.post(
        "/v1/tick",
        json={
            "now": "2026-04-26T10:35:00Z",
            "available_triggers": ["trg_001_research_digest_dentists"],
        },
    )
    assert response.status_code == 200
    actions = response.json()["actions"]
    assert len(actions) == 1
    action = actions[0]
    assert action["template_name"] == "vera_generic_v1"
    assert "JIDA" in action["body"]
    assert action["cta"] == "open_ended"
    assert action["send_as"] == "vera"


def test_tick_empty_when_trigger_missing(client):
    response = client.post(
        "/v1/tick",
        json={"now": "2026-04-26T10:35:00Z", "available_triggers": ["does_not_exist"]},
    )
    assert response.status_code == 200
    assert response.json()["actions"] == []


def test_tick_empty_when_expired(client):
    _seed_valid_trigger(client)
    response = client.post(
        "/v1/tick",
        json={
            "now": "2026-06-01T00:00:00Z",
            "available_triggers": ["trg_001_research_digest_dentists"],
        },
    )
    assert response.status_code == 200
    assert response.json()["actions"] == []


def test_tick_empty_list_is_valid(client):
    response = client.post("/v1/tick", json={"now": "2026-04-26T10:35:00Z", "available_triggers": []})
    assert response.status_code == 200
    assert response.json()["actions"] == []
