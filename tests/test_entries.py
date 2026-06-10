def create_account(client, name, tracked=True):
    return client.post(
        "/api/v1/accounts",
        json={
            "name": name,
            "type": "other",
            "date_of_start": "2025-01-01",
            "consider_for_networth": tracked,
        },
    ).json()


def test_snapshot_requires_all_accounts_and_rejects_duplicate(client):
    first = create_account(client, "First")
    second = create_account(client, "Second")
    incomplete = client.post(
        "/api/v1/snapshots",
        json={
            "date_of_entry": "2026-02-01",
            "accounts": [{"account_id": first["id"], "current_value": 1, "metric_entries": []}],
        },
    )
    assert incomplete.status_code == 422

    payload = {
        "date_of_entry": "2026-02-01",
        "accounts": [
            {"account_id": first["id"], "current_value": 100, "metric_entries": []},
            {"account_id": second["id"], "current_value": 200, "metric_entries": []},
        ],
    }
    assert client.post("/api/v1/snapshots", json=payload).status_code == 201
    assert client.post("/api/v1/snapshots", json=payload).status_code == 409


def test_individual_entries_only_for_excluded_accounts(client):
    tracked = create_account(client, "Tracked")
    excluded = create_account(client, "Excluded", tracked=False)
    data = {"date_of_entry": "2026-02-02", "current_value": 500, "metric_entries": []}

    assert client.post(f"/api/v1/accounts/{tracked['id']}/entries", json=data).status_code == 400
    response = client.post(f"/api/v1/accounts/{excluded['id']}/entries", json=data)
    assert response.status_code == 201
    entry_id = response.json()["id"]
    assert client.delete(f"/api/v1/entries/{entry_id}").status_code == 200
    assert client.get(f"/api/v1/accounts/{excluded['id']}/entries").json() == []


def test_metric_must_belong_to_account(client):
    first = create_account(client, "First", tracked=False)
    second = create_account(client, "Second", tracked=False)
    metric = client.post(
        f"/api/v1/accounts/{first['id']}/metrics",
        json={"name": "Yield", "is_percentage": True},
    ).json()
    response = client.post(
        f"/api/v1/accounts/{second['id']}/entries",
        json={
            "date_of_entry": "2026-03-01",
            "current_value": 100,
            "metric_entries": [{"metric_id": metric["id"], "value": 5}],
        },
    )
    assert response.status_code == 422
