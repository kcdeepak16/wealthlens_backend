import json
import logging
import re
import time
from datetime import datetime, time as daytime, timedelta
from zoneinfo import ZoneInfo

from .. import models
from ..database import settings
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

logger = logging.getLogger(__name__)
MAX_HISTORY_CHARS = 24000
MODEL_COOLDOWNS: dict[str, float] = {}


def configured_models() -> list[str]:
    names = [name.strip() for name in settings.gemini_models.split(",") if name.strip()]
    # Keep order, but avoid retrying the same model twice if configuration repeats it.
    return list(dict.fromkeys(names))


def compact_conversation(messages: list[dict], max_chars: int = MAX_HISTORY_CHARS) -> list[dict]:
    """Keep the user's original goal, recent turns, and latest preview SQL within a small budget."""
    if sum(len(message.get("content", "")) for message in messages) <= max_chars:
        return messages

    user_indices = [index for index, message in enumerate(messages) if message.get("role") == "user"]
    if not user_indices:
        return messages[-8:]
    first_user = user_indices[0]
    last_preview = next(
        (index for index in range(len(messages) - 1, -1, -1)
         if messages[index].get("role") == "assistant" and "Query used for this preview:" in messages[index].get("content", "")),
        None,
    )
    last_user = user_indices[-1]
    critical = {first_user, last_user}
    if last_preview is not None:
        critical.add(last_preview)

    compacted_by_index: dict[int, dict] = {}
    budget = max_chars
    for index in sorted(critical):
        message = messages[index]
        content = message.get("content", "")
        if index == last_preview:
            allowance = min(10000, max_chars // 2, budget)
        elif index == last_user:
            allowance = min(4000, max_chars // 4, budget)
        else:
            allowance = min(3000, max_chars // 5, budget)
        if allowance <= 0:
            continue
        compacted_by_index[index] = {"role": message.get("role", "user"), "content": _truncate_history_content(content, allowance)}
        budget -= len(compacted_by_index[index]["content"])

    other_indices = set(range(max(0, len(messages) - 12), len(messages)))
    other_indices.update(user_indices[-6:])
    other_indices.difference_update(critical)
    for index in sorted(other_indices, reverse=True):
        if budget <= 0:
            break
        message = messages[index]
        allowance = min(1800 if message.get("role") == "user" else 1200, budget)
        content = _truncate_history_content(message.get("content", ""), allowance)
        compacted_by_index[index] = {"role": message.get("role", "user"), "content": content}
        budget -= len(content)
    return [compacted_by_index[index] for index in sorted(compacted_by_index)]


def _truncate_history_content(content: str, allowance: int) -> str:
    if len(content) <= allowance:
        return content
    if "Query used for this preview:" in content:
        marker = "Query used for this preview:"
        head, _, sql = content.partition(marker)
        prefix = f"{head}{marker}\n"
        suffix = "\n[preview context shortened]"
        keep_sql = max(0, allowance - len(prefix) - len(suffix))
        return f"{prefix}{sql[:keep_sql]}{suffix}"
    suffix = "\n[older context shortened]"
    return content[: max(0, allowance - len(suffix))] + suffix


def _classify_model_error(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    if callable(code):
        try:
            code = code()
        except Exception:
            code = None
    status = getattr(exc, "status_code", None) or getattr(code, "value", None)
    detail = f"{type(exc).__name__} {exc} {code} {status}".lower()
    if any(token in detail for token in ("per_day", "perday", "per day", "daily quota", "quota_exceeded")):
        return "daily_quota"
    if str(status) == "429" or any(token in detail for token in ("resource_exhausted", "rate limit", "too many requests", "429")):
        return "rate_limit"
    if str(status) in {"500", "502", "503", "504"} or any(token in detail for token in ("service unavailable", "temporarily unavailable", "unavailable", "503", "internal server error", "deadline exceeded", "timed out", "connection reset")):
        return "service_unavailable"
    if str(status) == "404" or "model not found" in detail or "not supported for generatecontent" in detail:
        return "model_unavailable"
    return None


def _cooldown_seconds(kind: str) -> float:
    if kind == "daily_quota":
        pacific = ZoneInfo("America/Los_Angeles")
        now = datetime.now(pacific)
        next_midnight = datetime.combine(now.date() + timedelta(days=1), daytime.min, tzinfo=pacific)
        return max(60.0, (next_midnight - now).total_seconds() + 60.0)
    if kind == "rate_limit":
        return 60.0
    if kind == "model_unavailable":
        return 6 * 60 * 60.0
    return 30.0


def _send_with_model_failover(genai, models: list[str], system_prompt: str, history: list[dict], prompt: str, preferred: str | None = None) -> tuple[str, str]:
    now = time.monotonic()
    available = [name for name in models if MODEL_COOLDOWNS.get(name, 0) <= now]
    if preferred in available:
        available.remove(preferred)
        available.insert(0, preferred)
    if not available:
        raise RuntimeError("All configured Gemini models are cooling down after quota or service errors.")

    for model_name in available:
        try:
            model = genai.GenerativeModel(model_name, system_instruction=system_prompt)
            chat = model.start_chat(history=history)
            response = chat.send_message(
                prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": 2048},
            )
            MODEL_COOLDOWNS.pop(model_name, None)
            return response.text.strip(), model_name
        except Exception as exc:
            kind = _classify_model_error(exc)
            if kind is None:
                raise
            MODEL_COOLDOWNS[model_name] = time.monotonic() + _cooldown_seconds(kind)
            logger.warning("Gemini model %s failed (%s); trying the next configured model", model_name, kind)
    raise RuntimeError("All configured Gemini models failed due to quota or availability errors.")


def build_schema_context(db: Session) -> str:
    accounts = db.scalars(
        select(models.Account).options(selectinload(models.Account.metrics)).order_by(models.Account.name)
    ).all()
    account_lines = [
        f"- id={account.id}, name={account.name!r}, type={account.type!r}, "
        f"consider_for_networth={account.consider_for_networth}, metrics="
        + ", ".join(
            f"{metric.name} (is_percentage={metric.is_percentage}, metric_id={metric.id})"
            for metric in account.metrics
        )
        for account in accounts
    ]
    return """Database: WealthLens financial data.
Tables:
accounts(id, name, type, date_of_start, consider_for_networth)
metrics(id, account_id, name, is_percentage)
account_entries(id, account_id, date_of_entry, current_value)
metric_entries(id, account_entry_id, metric_id, value)
Relationships: accounts have metrics and account_entries; metric_entries join a metric to an account_entry.
Dates are DATE values; currency is INR. Use only these tables and columns. Queries must be a single read-only SELECT/CTE. Never use comments, multiple statements, DDL, DML, or procedural blocks. Return one SELECT result set. Limit large result sets to 200 rows.
Current accounts and available metric IDs:
""" + ("\n".join(account_lines) if account_lines else "(no accounts yet)")


def template_definitions():
    from ..routers.views import TEMPLATES
    return TEMPLATES


def _clean_json(raw: str) -> dict:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    return json.loads(clean)


def generate_view(messages: list[dict], db: Session, max_self_corrections: int = 3) -> dict:
    if not settings.gemini_api_key:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="AI service not configured. Please set GEMINI_API_KEY.")

    model_names = configured_models()
    if not model_names:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="AI service not configured. Please set GEMINI_MODELS.")

    import google.generativeai as genai
    from fastapi import HTTPException
    from ..routers.views import TEMPLATES, execute_view_query, validate_view_config

    try:
        genai.configure(api_key=settings.gemini_api_key)
        descriptions = "\n".join(f"{key}: {value['description']}" for key, value in TEMPLATES.items())
        system_prompt = f"""You are WealthLens' saved view assistant. Use the schema below. Ask one concise clarification if the request is ambiguous. Otherwise emit ONLY JSON. For a query use {{"type":"query","title":"up to 8 words","sql":"SELECT ...","template":"one ID","config":{{...}}}}. For clarification use {{"type":"question","message":"..."}}. For a request that cannot be fulfilled after retries use {{"type":"failure","message":"plain English explanation"}}. Available templates and their purpose: {descriptions}
Required config keys: {json.dumps({key: value['required_keys'] for key, value in TEMPLATES.items()})}
Output selection: if the user explicitly asks for a list, table, or rows, use data_table. If they ask for a ranked/top list, use ranked_list. Do not choose a chart unless the user asks for a chart/graph or clearly wants a visual trend. For monthly comparisons, a requested list should include one row per month and all requested change columns (for example month, portfolio_value, month_on_month_increase).
For “first entry of each month”, find the earliest date_of_entry in each calendar month, aggregate current_value across the included accounts on that date, then calculate the difference from the prior available month when requested. For portfolio totals, include only accounts with consider_for_networth = TRUE unless the user asks to include excluded accounts. For a list/table with a month-on-month increase, return aliases exactly named month, portfolio_value, and month_on_month_increase. Use month_on_month_increase for the absolute currency difference from the prior available month (use LAG over ascending month), and set config.is_currency=true so all monetary columns are formatted as INR. PostgreSQL DATE_TRUNC, EXTRACT, CTEs, and window functions are permitted in a read-only SELECT when they help answer the request. Do not invent function restrictions. If a validation/execution error is returned below, correct the query while preserving the user's requested presentation and columns.
Security: only a single read-only SELECT/CTE. Do not emit comments, semicolons, DML, DDL, or PL/pgSQL. Use the exact schema fields and actual metric IDs.\n{build_schema_context(db)}"""
        history = []
        compacted_messages = compact_conversation(messages)
        for message in compacted_messages[:-1]:
            history.append({"role": "user" if message["role"] == "user" else "model", "parts": [message["content"]]})
        current_messages = list(compacted_messages)
        latest_user_request = next(
            (message["content"] for message in reversed(messages) if message["role"] == "user"),
            "",
        )
        asks_for_table = bool(re.search(r"\b(list form|in a list|as a list|table form|as a table|tabular)\b", latest_user_request, re.I))
        asks_for_month_change = bool(re.search(r"\b(month[ -]on[ -]month|month[ -]over[ -]month|mom)\b", latest_user_request, re.I))
        preferred_model = None
        for attempt in range(max_self_corrections):
            raw, preferred_model = _send_with_model_failover(
                genai,
                model_names,
                system_prompt,
                history,
                current_messages[-1]["content"],
                preferred=preferred_model,
            )
            try:
                parsed = _clean_json(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("The response must be one JSON object.")
            except (json.JSONDecodeError, TypeError, ValueError):
                history.extend([
                    {"role": "model", "parts": [raw]},
                    {"role": "user", "parts": ["That was not valid JSON in the required response format. Return only one JSON object with type question, query, or failure. Do not include prose or markdown."]},
                ])
                current_messages = [{"role": "user", "content": "Return the response in the required JSON format."}]
                continue
            kind = parsed.get("type")
            if kind in ("question", "failure"):
                if not isinstance(parsed.get("message"), str) or not parsed["message"].strip():
                    history.extend([
                        {"role": "model", "parts": [raw]},
                        {"role": "user", "parts": ["The JSON message field is missing or empty. Return a corrected JSON object."]},
                    ])
                    current_messages = [{"role": "user", "content": "Return a corrected JSON object."}]
                    continue
                return {"type": kind, "message": str(parsed.get("message", "Could you clarify your request?"))}
            if kind != "query":
                error = "The response format was invalid. Return the requested JSON format."
            else:
                sql = parsed.get("sql", "")
                template = parsed.get("template", "")
                config = parsed.get("config", {})
                try:
                    if not isinstance(sql, str) or not sql.strip():
                        raise ValueError("The query field is missing or empty.")
                    if not isinstance(config, dict):
                        raise ValueError("The visualization config must be a JSON object.")
                    if template not in TEMPLATES:
                        raise ValueError("Choose one of the available visualization templates.")
                    if asks_for_table and template != "data_table":
                        raise ValueError("The user explicitly asked for list/table form. Use the data_table template.")
                    validate_view_config(template, config)
                    result = execute_view_query(db, sql)
                    if not result["success"]:
                        raise ValueError(result["error"])
                    columns = set(result["columns"])
                    validate_view_config(template, config, columns=columns, allow_empty=not columns)
                    if asks_for_month_change:
                        required_columns = {"month", "portfolio_value", "month_on_month_increase"}
                        if not required_columns.issubset(columns):
                            raise ValueError(
                                "For the requested month-on-month table, return columns named month, "
                                "portfolio_value, and month_on_month_increase."
                            )
                    return {"type": "preview", "title": str(parsed.get("title") or "Custom View")[:100], "sql_query": sql, "template": template, "config": config, "data": result["data"], "row_count": result["row_count"], "message": "Here's what I found. Does this look right?"}
                except Exception as exc:
                    error = str(exc)
            history.extend([
                {"role": "model", "parts": [raw]},
                {"role": "user", "parts": [f"The query was rejected or failed: {error}. Please correct it and return JSON."]},
            ])
            current_messages = [{"role": "user", "content": "Please correct the last query."}]
        return {"type": "failure", "message": "I couldn't build a safe query that works with the available data. Try narrowing the request or specifying the accounts, metric, or time period."}
    except HTTPException:
        raise
    except Exception as exc:
        # Keep provider internals and credentials out of API responses.
        raise HTTPException(status_code=502, detail="AI service unavailable. Please try again.") from exc
