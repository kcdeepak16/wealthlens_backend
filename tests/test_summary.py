from datetime import date


def create_account(client, name, account_type="bank_account", tracked=True):
    return client.post(
        "/api/v1/accounts",
        json={
            "name": name,
            "type": account_type,
            "date_of_start": "2024-01-01",
            "consider_for_networth": tracked,
        },
    ).json()


def test_empty_summary(client):
    summary = client.get("/api/v1/summary")
    assert summary.status_code == 200
    assert summary.json()["current_net_worth"] == 0
    assert summary.json()["summary_metrics"]["entries_logged"] == 0


def test_summary_history_chart_and_metrics(client):
    bank = create_account(client, "Bank")
    fund = create_account(client, "Fund", "mutual_fund")
    metric = client.post(
        f"/api/v1/accounts/{fund['id']}/metrics",
        json={"name": "XIRR", "is_percentage": True},
    ).json()

    for entry_date, bank_value, fund_value, xirr in [
        ("2026-01-01", 1000, 2000, 8),
        ("2026-02-01", 1200, 2400, 9),
    ]:
        response = client.post(
            "/api/v1/snapshots",
            json={
                "date_of_entry": entry_date,
                "accounts": [
                    {"account_id": bank["id"], "current_value": bank_value, "metric_entries": []},
                    {
                        "account_id": fund["id"],
                        "current_value": fund_value,
                        "metric_entries": [{"metric_id": metric["id"], "value": xirr}],
                    },
                ],
            },
        )
        assert response.status_code == 201

    history = client.get("/api/v1/networth/history?range=all").json()
    assert [point["net_worth"] for point in history] == [3000, 3600]

    summary = client.get("/api/v1/summary").json()
    assert summary["current_net_worth"] == 3600
    assert summary["previous_net_worth"] == 3000
    assert round(summary["change_percent"], 1) == 20
    assert summary["summary_metrics"]["entries_logged"] == 2
    assert summary["summary_metrics"]["avg_entry_gap_days"] == 31
    assert summary["summary_metrics"]["portfolio_age_days"] == (date.today() - date(2024, 1, 1)).days

    chart = client.get(f"/api/v1/accounts/{fund['id']}/chart-data?range=all").json()
    assert [point["value"] for point in chart["value_series"]] == [2000, 2400]
    assert [point["value"] for point in chart["metric_series"][0]["data"]] == [8, 9]


def test_new_account_without_entries_does_not_zero_dashboard(client):
    bank = create_account(client, "Bank")
    assert client.post(
        "/api/v1/snapshots",
        json={
            "date_of_entry": "2026-01-01",
            "accounts": [{"account_id": bank["id"], "current_value": 1000, "metric_entries": []}],
        },
    ).status_code == 201

    create_account(client, "New Empty Account")

    summary = client.get("/api/v1/summary").json()
    history = client.get("/api/v1/networth/history?range=all").json()
    assert summary["current_net_worth"] == 1000
    assert history[-1]["net_worth"] == 1000


def test_clear_all_data_endpoint_is_removed(client):
    create_account(client, "Bank")
    assert client.delete("/api/v1/data/all").status_code == 404
    assert len(client.get("/api/v1/accounts").json()) == 1
