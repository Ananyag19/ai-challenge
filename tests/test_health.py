from tests.conftest import push_context


def test_healthz_initial_counts(client):
    response = client.get("/v1/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0
    assert body["contexts_loaded"] == {
        "category": 0,
        "merchant": 0,
        "customer": 0,
        "trigger": 0,
    }


def test_healthz_counts_after_push(client):
    assert push_context(client, "category", "dentists", 1, {"slug": "dentists"}).status_code == 200
    assert push_context(
        client,
        "merchant",
        "m_001",
        1,
        {"merchant_id": "m_001", "category_slug": "dentists"},
    ).status_code == 200
    assert push_context(client, "merchant", "m_001", 2, {"merchant_id": "m_001"}).status_code == 200

    body = client.get("/v1/healthz").json()
    assert body["contexts_loaded"]["category"] == 1
    assert body["contexts_loaded"]["merchant"] == 1
