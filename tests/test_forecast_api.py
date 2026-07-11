def test_forecast_config_endpoint(client):
    response = client.get("/api/v1/forecast/config")
    assert response.status_code == 200
    data = response.json()
    assert "account_types" in data
    assert "default_inflation_rate" in data


def test_forecast_config_no_accounts_returns_empty_list(client):
    response = client.get("/api/v1/forecast/config")
    assert response.status_code == 200
    assert isinstance(response.json()["account_types"], list)


def test_forecast_projection_endpoint(client):
    payload = {
        "account_types": [
            {"account_type": "mutual_fund", "monthly_sip": 10000, "rate_percent": 12.0}
        ],
        "step_up_percent": 10.0,
        "additional_investment": 50000,
        "inflation_rate_percent": 6.0,
        "years": 10,
    }
    response = client.post("/api/v1/forecast/projection", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["years"]) == 10
    assert data["years"][0]["calendar_year"] > 2026


def test_forecast_projection_persists_settings(client):
    payload = {
        "account_types": [{"account_type": "stocks", "monthly_sip": 5000, "rate_percent": 14.0}],
        "step_up_percent": 5.0,
        "additional_investment": 0,
        "inflation_rate_percent": 6.0,
        "years": 10,
    }
    client.post("/api/v1/forecast/projection", json=payload)
    config = client.get("/api/v1/forecast/config").json()
    assert config["saved_inputs"] is not None
    assert config["saved_inputs"]["step_up_percent"] == 5.0


def test_forecast_config_uses_latest_account_type_profit_for_default_rate(client):
    account = client.post(
        "/api/v1/accounts",
        json={
            "name": "Fund",
            "type": "mutual_fund",
            "date_of_start": "2026-01-01",
            "consider_for_networth": True,
        },
    ).json()
    client.post(
        "/api/v1/forecast/projection",
        json={
            "account_types": [
                {"account_type": "mutual_fund", "monthly_sip": 5000, "rate_percent": 8.0}
            ],
            "step_up_percent": 5.0,
            "additional_investment": 0,
            "inflation_rate_percent": 6.0,
            "years": 10,
        },
    )
    client.post(
        "/api/v1/snapshots",
        json={
            "date_of_entry": "2026-07-12",
            "accounts": [{"account_id": account["id"], "current_value": 100000, "metric_entries": []}],
            "account_type_profits": [
                {"account_type": "mutual_fund", "profit_percentage": 13.75}
            ],
        },
    )

    config = client.get("/api/v1/forecast/config").json()
    mutual_fund = next(item for item in config["account_types"] if item["account_type"] == "mutual_fund")
    assert mutual_fund["default_rate_percent"] == 13.75
    assert mutual_fund["has_profit_history"] is True
    assert config["saved_inputs"]["account_types"][0]["rate_percent"] == 8.0


def test_forecast_fire_endpoint(client):
    payload = {
        "retirement_year": 10,
        "starting_corpus": 20_000_000,
        "monthly_expense_today": 60000,
        "inflation_rate_percent": 6.0,
        "post_retirement_growth_percent": 8.0,
        "max_years": 50,
    }
    response = client.post("/api/v1/forecast/fire", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "rows" in data
    assert "sustainable" in data
    assert data["starting_corpus"] == 20_000_000
