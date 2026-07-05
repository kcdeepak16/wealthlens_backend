def test_snapshot_prefill_endpoint(client):
    response = client.get("/api/v1/snapshots/prefill")
    assert response.status_code == 200
    data = response.json()
    assert "accounts" in data
    assert "account_type_profits" in data


def test_snapshot_prefill_returns_null_for_no_history(client):
    account = client.post(
        "/api/v1/accounts",
        json={
            "name": "New Test Account",
            "type": "other",
            "date_of_start": "2026-07-01",
            "consider_for_networth": True,
        },
    ).json()
    response = client.get("/api/v1/snapshots/prefill")
    matching = next(
        (item for item in response.json()["accounts"] if item["account_id"] == account["id"]),
        None,
    )
    assert matching is not None
    assert matching["last_current_value"] is None


def test_snapshot_with_account_type_profit(client):
    account = client.post(
        "/api/v1/accounts",
        json={
            "name": "Fund",
            "type": "mutual_fund",
            "date_of_start": "2026-07-01",
            "consider_for_networth": True,
        },
    ).json()
    payload = {
        "date_of_entry": "2026-07-05",
        "accounts": [{"account_id": account["id"], "current_value": 1000, "metric_entries": []}],
        "account_type_profits": [{"account_type": "mutual_fund", "profit_percentage": 15.5}],
    }
    assert client.post("/api/v1/snapshots", json=payload).status_code == 201
    prefill = client.get("/api/v1/snapshots/prefill").json()
    matching = next(
        item for item in prefill["account_type_profits"] if item["account_type"] == "mutual_fund"
    )
    assert matching["last_profit_percentage"] == 15.5


def test_delete_all_data_endpoint_removed(client):
    response = client.delete("/api/v1/data/all")
    assert response.status_code == 404
