from tests.conftest import push_context


def test_context_accepts_valid_push(client):
    response = push_context(client, "category", "dentists", 1, {"slug": "dentists"})
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["ack_id"] == "ack_dentists_v1"
    assert "stored_at" in body


def test_same_version_is_idempotent_noop(client):
    first = push_context(client, "merchant", "m_001", 1, {"name": "A"})
    assert first.status_code == 200
    stored_at = first.json()["stored_at"]

    second = push_context(client, "merchant", "m_001", 1, {"name": "B"})
    assert second.status_code == 200
    assert second.json()["accepted"] is True
    assert second.json()["stored_at"] == stored_at

    counts = client.get("/v1/healthz").json()["contexts_loaded"]
    assert counts["merchant"] == 1


def test_lower_version_is_stale(client):
    assert push_context(client, "merchant", "m_001", 3, {"v": 3}).status_code == 200
    stale = push_context(client, "merchant", "m_001", 2, {"v": 2})
    assert stale.status_code == 409
    body = stale.json()
    assert body["accepted"] is False
    assert body["reason"] == "stale_version"
    assert body["current_version"] == 3


def test_higher_version_replaces_atomically(client):
    assert push_context(client, "customer", "c_001", 1, {"name": "Priya"}).status_code == 200
    bumped = push_context(client, "customer", "c_001", 2, {"name": "Priya Updated"})
    assert bumped.status_code == 200
    assert bumped.json()["accepted"] is True
    assert bumped.json()["ack_id"] == "ack_c_001_v2"
    counts = client.get("/v1/healthz").json()["contexts_loaded"]
    assert counts["customer"] == 1


def test_unknown_scope_is_400(client):
    response = push_context(client, "unknown", "x", 1, {})
    assert response.status_code == 400
    body = response.json()
    assert body["accepted"] is False
    assert body["reason"] == "invalid_scope"


def test_malformed_context_is_400(client):
    response = client.post("/v1/context", json={"scope": "category"})
    assert response.status_code == 400
    assert response.json()["accepted"] is False
