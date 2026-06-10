def test_metric_crud(client, account_payload):
    account_id = client.post("/api/v1/accounts", json=account_payload).json()["id"]
    created = client.post(
        f"/api/v1/accounts/{account_id}/metrics",
        json={"name": "XIRR", "is_percentage": True},
    )
    assert created.status_code == 201
    metric_id = created.json()["id"]

    updated = client.put(
        f"/api/v1/metrics/{metric_id}",
        json={"name": "Annual return", "is_percentage": True},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Annual return"
    assert client.delete(f"/api/v1/metrics/{metric_id}").status_code == 200


def test_metric_account_must_exist(client):
    assert (
        client.post(
            "/api/v1/accounts/999/metrics",
            json={"name": "Rate", "is_percentage": True},
        ).status_code
        == 404
    )
