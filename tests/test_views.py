import pytest


def test_save_list_run_rename_delete_view(client):
    response = client.post("/api/v1/views", json={
        "title": "Account Count", "prompt": "Count accounts", "sql_query": "SELECT COUNT(*) AS count FROM accounts",
        "template": "stat_card", "config": {"value_key": "count"},
    })
    assert response.status_code == 200
    view_id = response.json()["id"]
    assert client.get("/api/v1/views").json()[0]["title"] == "Account Count"
    run = client.get(f"/api/v1/views/{view_id}/run")
    assert run.status_code == 200
    assert run.json()["data"][0]["count"] == 0
    assert run.json()["row_count"] == 1
    assert client.patch(f"/api/v1/views/{view_id}", json={"title": "Accounts Total"}).json()["title"] == "Accounts Total"
    assert client.delete(f"/api/v1/views/{view_id}").json() == {"deleted": True}
    assert client.get(f"/api/v1/views/{view_id}/run").status_code == 404


def test_run_view_bad_sql_returns_safe_error(client):
    saved = client.post("/api/v1/views", json={
        "title": "Bad view", "prompt": "Test", "sql_query": "SELECT no_such_column FROM accounts",
        "template": "data_table", "config": {},
    })
    assert saved.status_code == 200
    run = client.get(f"/api/v1/views/{saved.json()['id']}/run")
    assert run.status_code == 500
    assert "no_such_column" not in run.json()["detail"]


def test_write_queries_are_rejected(client):
    for sql in (
        "DELETE FROM accounts", "SELECT 1; DROP TABLE accounts", "WITH removed AS (DELETE FROM accounts RETURNING id) SELECT * FROM removed",
        "SELECT pg_sleep(1)", "SELECT 1 FOR UPDATE", "SELECT * FROM accounts, pg_catalog.pg_class",
        "SELECT pg_notify('x', 'y')",
    ):
        response = client.post("/api/v1/views", json={
            "title": "Unsafe", "prompt": "Test", "sql_query": sql, "template": "data_table", "config": {},
        })
        assert response.status_code == 422, sql


def test_template_config_must_be_valid(client):
    response = client.post("/api/v1/views", json={
        "title": "Invalid", "prompt": "Test", "sql_query": "SELECT 1 AS count", "template": "stat_card", "config": {},
    })
    assert response.status_code == 422


def test_generate_without_gemini_key_returns_503(client, monkeypatch):
    from app.database import settings
    monkeypatch.setattr(settings, "gemini_api_key", "")
    response = client.post("/api/v1/views/generate", json={"messages": [{"role": "user", "content": "Show me a useful view"}]})
    assert response.status_code == 503
    assert response.json()["detail"] == "AI service not configured. Please set GEMINI_API_KEY."


def test_generate_retries_non_json_ai_response(client, monkeypatch):
    import google.generativeai as genai
    from app.database import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    replies = iter([
        "The previous query failed due to restrictions. I will simplify it.",
        '{"type":"query","title":"Monthly Portfolio","sql":"SELECT \'2026-01-01\' AS month, 100 AS portfolio_value, NULL AS month_on_month_increase","template":"line_chart","config":{"x_key":"month","y_key":"portfolio_value"}}',
        '{"type":"query","title":"Monthly Portfolio","sql":"SELECT \'2026-01-01\' AS month, 100 AS portfolio_value, NULL AS month_on_month_increase","template":"data_table","config":{}}',
    ])
    send_calls = []

    class FakeChat:
        def send_message(self, content, **kwargs):
            send_calls.append(content)
            return type("Response", (), {"text": next(replies)})()

    class FakeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def start_chat(self, **_kwargs):
            return FakeChat()

    monkeypatch.setattr(genai, "GenerativeModel", FakeModel)
    response = client.post("/api/v1/views/generate", json={"messages": [
        {"role": "user", "content": "In list form, show monthly portfolio values and the month-on-month increase."},
    ]})
    assert response.status_code == 200
    assert response.json()["type"] == "preview"
    assert response.json()["template"] == "data_table"
    assert response.json()["data"][0]["portfolio_value"] == 100
    assert len(send_calls) == 3


def test_read_only_validator_allows_monthly_cte_and_window_functions():
    from app.routers.views import validate_read_only_sql

    sql = """WITH monthly AS (
        SELECT DATE_TRUNC('month', date_of_entry)::date AS month, SUM(current_value) AS portfolio_value
        FROM account_entries GROUP BY DATE_TRUNC('month', date_of_entry)
    ), changes AS (
        SELECT month, portfolio_value, portfolio_value - LAG(portfolio_value) OVER (ORDER BY month) AS month_on_month_increase
        FROM monthly
    ) SELECT month, portfolio_value, month_on_month_increase FROM changes ORDER BY month"""
    assert validate_read_only_sql(sql) == sql


@pytest.mark.parametrize("failure_message", [
    "429 RESOURCE_EXHAUSTED: generate_requests_per_model_per_day",
    "503 Service Unavailable: backend overloaded",
])
def test_generate_fails_over_and_reuses_context_after_model_errors(client, monkeypatch, failure_message):
    import google.generativeai as genai
    from app.database import settings
    from app.services import gemini

    gemini.MODEL_COOLDOWNS.clear()
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_models", "primary-model,backup-model")
    calls = []

    class FakeChat:
        def __init__(self, model_name, history):
            self.model_name = model_name
            self.history = history

        def send_message(self, content, **kwargs):
            calls.append((self.model_name, content, self.history))
            if self.model_name == "primary-model":
                raise RuntimeError(failure_message)
            return type("Response", (), {"text": '{"type":"query","title":"Account Count","sql":"SELECT COUNT(*) AS total FROM accounts","template":"data_table","config":{}}'})()

    class FakeModel:
        def __init__(self, model_name, **_kwargs):
            self.model_name = model_name

        def start_chat(self, history):
            return FakeChat(self.model_name, history)

    monkeypatch.setattr(genai, "GenerativeModel", FakeModel)
    request = {"messages": [
        {"role": "user", "content": "Show account count."},
        {"role": "assistant", "content": "Earlier query SQL: SELECT COUNT(*) FROM accounts"},
        {"role": "user", "content": "Keep the same data but as a list."},
    ]}
    first = client.post("/api/v1/views/generate", json=request)
    second = client.post("/api/v1/views/generate", json=request)
    assert first.status_code == second.status_code == 200
    assert first.json()["type"] == second.json()["type"] == "preview"
    assert [call[0] for call in calls] == ["primary-model", "backup-model", "backup-model"]
    assert calls[0][2] == calls[1][2] == calls[2][2]
    gemini.MODEL_COOLDOWNS.clear()


def test_compact_conversation_keeps_initial_request_preview_sql_and_recent_turns():
    from app.services.gemini import compact_conversation

    messages = [
        {"role": "user", "content": "Original monthly portfolio request"},
        {"role": "assistant", "content": "Preview metadata: template=line_chart\nQuery used for this preview:\nSELECT month, total FROM monthly"},
        *[{"role": "assistant", "content": "older explanation " * 1200} for _ in range(20)],
        {"role": "user", "content": "Final request: use a table and include monthly increase"},
    ]
    compacted = compact_conversation(messages, max_chars=10000)
    content = "\n".join(message["content"] for message in compacted)
    assert "Original monthly portfolio request" in content
    assert "SELECT month, total FROM monthly" in content
    assert "Final request: use a table" in content
    assert sum(len(message["content"]) for message in compacted) <= 10000


def test_saved_chat_crud_preserves_preview_context(client):
    messages = [
        {"role": "user", "content": "Show monthly portfolio value"},
        {
            "role": "assistant",
            "content": "Here's what I found. Does this look right?",
            "context_content": "Preview metadata: template=data_table\nQuery used for this preview:\nSELECT 1 AS value",
            "preview": {
                "type": "preview", "message": "Here's what I found. Does this look right?",
                "sql_query": "SELECT 1 AS value", "template": "data_table", "config": {},
                "data": [{"value": 1}], "row_count": 1, "title": "Monthly Portfolio",
            },
        },
    ]
    created = client.post("/api/v1/views/chats", json={"messages": messages})
    assert created.status_code == 200
    chat_id = created.json()["id"]
    assert created.json()["title"] == "Show monthly portfolio value"
    assert created.json()["messages"][1]["preview"]["data"] == [{"value": 1}]
    assert client.get("/api/v1/views/chats").json()[0]["message_count"] == 2

    updated = client.put("/api/v1/views/chats/" + str(chat_id), json={
        "title": "Monthly portfolio draft",
        "messages": messages + [{"role": "user", "content": "Also include the monthly change."}],
    })
    assert updated.status_code == 200
    assert updated.json()["title"] == "Monthly portfolio draft"
    assert len(client.get(f"/api/v1/views/chats/{chat_id}").json()["messages"]) == 3
    assert client.delete(f"/api/v1/views/chats/{chat_id}").json() == {"deleted": True}
    assert client.get(f"/api/v1/views/chats/{chat_id}").status_code == 404
