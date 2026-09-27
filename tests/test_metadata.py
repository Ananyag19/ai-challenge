def test_metadata_from_settings(client):
    response = client.get("/v1/metadata")
    assert response.status_code == 200
    body = response.json()
    assert body["team_name"] == "Test Team"
    assert body["team_members"] == ["Ada", "Bob"]
    assert body["model"] == "none"
    assert body["approach"] == "foundation tests"
    assert body["contact_email"] == "test@example.com"
    assert body["version"] == "0.1.0-test"
    assert body["submitted_at"] == "2026-04-26T08:00:00Z"
    assert "anany" not in body["contact_email"].lower()
