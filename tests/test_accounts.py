def test_account_crud_and_cascade(client, account_payload):
    created = client.post("/api/v1/accounts", json=account_payload)
    assert created.status_code == 201
    account_id = created.json()["id"]

    metric = client.post(
        f"/api/v1/accounts/{account_id}/metrics",
        json={"name": "Interest rate", "is_percentage": True},
    )
    assert metric.status_code == 201

    snapshot = client.post(
        "/api/v1/snapshots",
        json={
            "date_of_entry": "2026-01-01",
            "accounts": [{"account_id": account_id, "current_value": 10000, "metric_entries": []}],
        },
    )
    assert snapshot.status_code == 201

    accounts = client.get("/api/v1/accounts")
    assert accounts.status_code == 200
    assert accounts.json()[0]["current_value"] == 10000

    updated = client.put(
        f"/api/v1/accounts/{account_id}", json={"name": "Primary Salary Account"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Primary Salary Account"

    deleted = client.delete(f"/api/v1/accounts/{account_id}")
    assert deleted.status_code == 200
    assert client.get("/api/v1/accounts").json() == []


def test_rejects_invalid_account_type(client, account_payload):
    account_payload["type"] = "crypto"
    assert client.post("/api/v1/accounts", json=account_payload).status_code == 422
