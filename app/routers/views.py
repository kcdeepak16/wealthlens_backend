from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.gemini import generate_view

router = APIRouter(tags=["views"])

TEMPLATES = {
    "line_chart": {"description": "Time series trend with date/category and numeric value.", "required_keys": ["x_key", "y_key"], "optional_keys": ["series_key"]},
    "bar_chart": {"description": "Compare numeric values across categories.", "required_keys": ["x_key", "y_key"], "optional_keys": ["color_key"]},
    "pie_chart": {"description": "Show how a meaningful total is split across categories.", "required_keys": ["name_key", "value_key"], "optional_keys": []},
    "stat_card": {"description": "Show a single aggregate value.", "required_keys": ["value_key"], "optional_keys": ["label_key", "subtitle_key"]},
    "ranked_list": {"description": "Show an ordered ranking with names and values.", "required_keys": ["name_key", "value_key"], "optional_keys": ["rank_key", "subtitle_key"]},
    "data_table": {"description": "Show multi-column tabular data.", "required_keys": [], "optional_keys": []},
}

_FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE|CALL|DO|COPY|VACUUM|ATTACH|DETACH|PRAGMA|GRANT|REVOKE|SET|RESET|INTO|EXEC|EXECUTE)\b", re.I)
_UNSAFE_FUNCTIONS = re.compile(r"\b(pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_notify|pg_advisory_lock|pg_advisory_xact_lock|pg_advisory_unlock|lo_[a-z_]+|dblink[a-z_]*|nextval|setval|set_config)\s*\(", re.I)
_ALLOWED_TABLES = {"accounts", "metrics", "account_entries", "metric_entries"}


def validate_read_only_sql(sql: str) -> str:
    if not sql or len(sql) > 12000:
        raise ValueError("Query is empty or too long.")
    candidate = sql.strip()
    # Permit one optional trailing semicolon only; never permit a second statement.
    candidate = candidate[:-1].rstrip() if candidate.endswith(";") else candidate
    if ";" in candidate:
        raise ValueError("Only one SQL statement is allowed.")
    if "--" in candidate or "/*" in candidate or "*/" in candidate:
        raise ValueError("SQL comments are not allowed.")
    scrubbed = re.sub(r"'(?:''|\\.|[^'])*'|\"(?:\"\"|\\.|[^\"])*\"", " ", candidate)
    if not re.match(r"^(SELECT|WITH)\b", scrubbed, re.I):
        raise ValueError("Only read-only SELECT queries are allowed.")
    if _FORBIDDEN.search(scrubbed) or _UNSAFE_FUNCTIONS.search(scrubbed):
        raise ValueError("The query contains a prohibited SQL operation.")
    if '"' in candidate or "`" in candidate or "[" in candidate:
        raise ValueError("Quoted identifiers are not allowed in view queries.")
    if re.search(r"\bFROM\s+[a-zA-Z_]\w*(?:\s+(?:AS\s+)?[a-zA-Z_]\w*)?\s*,", scrubbed, re.I):
        raise ValueError("Comma-separated table references are not allowed; use explicit JOIN clauses.")
    ctes = {name.lower() for name in re.findall(r"(?:\bWITH(?:\s+RECURSIVE)?\b|,)\s*([a-zA-Z_]\w*)\s+AS\s*\(", scrubbed, re.I)}
    referenced_tables = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)?)", scrubbed, re.I)
    if any(name.lower() not in _ALLOWED_TABLES and name.lower() not in ctes for name in referenced_tables):
        raise ValueError("Queries may only read WealthLens account and metric tables.")
    if re.search(r"\bFOR\s+(UPDATE|SHARE|NO\s+KEY\s+UPDATE|KEY\s+SHARE)\b", scrubbed, re.I):
        raise ValueError("Locking clauses are not allowed.")
    return candidate


def validate_view_config(template: str, config: dict[str, Any], columns: set[str] | None = None, allow_empty: bool = False) -> None:
    if template not in TEMPLATES:
        raise ValueError("Unknown visualization template.")
    if not isinstance(config, dict):
        raise ValueError("Visualization config must be an object.")
    definition = TEMPLATES[template]
    for key in definition["required_keys"]:
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"Visualization config requires {key}.")
    for key in definition["required_keys"] + definition["optional_keys"]:
        value = config.get(key)
        if value is not None and (not isinstance(value, str) or (columns is not None and value not in columns)):
            raise ValueError(f"Visualization field {key} must refer to a result column.")
        if columns is not None and not columns and not allow_empty:
            raise ValueError("Query returned no columns.")


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def execute_view_query(db: Session, sql: str) -> dict:
    try:
        safe_sql = validate_read_only_sql(sql)
        result = db.execute(text(safe_sql))
        columns = list(result.keys())
        rows = [
            {column: _json_value(value) for column, value in zip(columns, row)}
            for row in result.fetchmany(501)
        ]
        if len(rows) > 500:
            rows = rows[:500]
        return {"success": True, "data": rows, "row_count": len(rows), "columns": columns}
    except Exception as exc:
        db.rollback()
        return {"success": False, "error": str(exc), "data": [], "row_count": 0, "columns": []}


def _run_result(view_id: int | None, title: str, template: str, config: dict, sql: str, db: Session):
    validate_view_config(template, config)
    result = execute_view_query(db, sql)
    if not result["success"]:
        raise HTTPException(status_code=500, detail="Saved view query failed. The underlying data may have changed.")
    columns = set(result["columns"])
    validate_view_config(template, config, columns=columns, allow_empty=not columns)
    return schemas.ViewRunResult(view_id=view_id, title=title, template=template, config=config, **{key: result[key] for key in ("data", "row_count")})


@router.post("/views/generate", response_model=schemas.ViewGenerateResponse)
def generate_view_endpoint(request: schemas.ViewGenerateRequest, db: Session = Depends(get_db)):
    messages = [message.model_dump() for message in request.messages]
    return generate_view(messages, db)


@router.get("/views", response_model=list[schemas.SavedViewOut])
def list_views(db: Session = Depends(get_db)):
    return db.query(models.SavedView).order_by(models.SavedView.created_at.desc(), models.SavedView.id.desc()).all()


@router.post("/views", response_model=schemas.SavedViewOut)
def save_view(request: schemas.ViewConfirmRequest, db: Session = Depends(get_db)):
    try:
        validate_read_only_sql(request.sql_query)
        validate_view_config(request.template, request.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    view = models.SavedView(**request.model_dump())
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


@router.get("/views/{view_id}/run", response_model=schemas.ViewRunResult)
def run_view(view_id: int, db: Session = Depends(get_db)):
    view = db.get(models.SavedView, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    result = _run_result(view.id, view.title, view.template, view.config, view.sql_query, db)
    view.last_run_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return result


@router.patch("/views/{view_id}", response_model=schemas.SavedViewOut)
def update_view(view_id: int, request: schemas.ViewUpdateRequest, db: Session = Depends(get_db)):
    view = db.get(models.SavedView, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    view.title = request.title.strip()
    db.commit()
    db.refresh(view)
    return view


@router.delete("/views/{view_id}")
def delete_view(view_id: int, db: Session = Depends(get_db)):
    view = db.get(models.SavedView, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    db.delete(view)
    db.commit()
    return {"deleted": True}


def _saved_chat_messages(messages: list[schemas.SavedChatMessage]) -> list[dict]:
    return [message.model_dump(exclude_none=True) for message in messages]


def _saved_chat_title(requested_title: str | None, messages: list[schemas.SavedChatMessage]) -> str:
    if requested_title and requested_title.strip():
        return " ".join(requested_title.split())[:100]
    first_user_message = next((message.content for message in messages if message.role == "user"), "Saved chat")
    title = " ".join(first_user_message.split())
    return title[:97] + "…" if len(title) > 100 else title or "Saved chat"


@router.get("/views/chats", response_model=list[schemas.SavedViewChatSummary])
def list_saved_chats(db: Session = Depends(get_db)):
    chats = db.query(models.SavedViewChat).order_by(models.SavedViewChat.updated_at.desc(), models.SavedViewChat.id.desc()).all()
    return [
        schemas.SavedViewChatSummary(
            id=chat.id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            message_count=len(chat.messages),
        )
        for chat in chats
    ]


@router.post("/views/chats", response_model=schemas.SavedViewChatOut)
def create_saved_chat(request: schemas.SavedViewChatCreate, db: Session = Depends(get_db)):
    messages = _saved_chat_messages(request.messages)
    chat = models.SavedViewChat(
        title=_saved_chat_title(request.title, request.messages),
        messages=messages,
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.get("/views/chats/{chat_id}", response_model=schemas.SavedViewChatOut)
def get_saved_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.get(models.SavedViewChat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Saved chat not found")
    return chat


@router.put("/views/chats/{chat_id}", response_model=schemas.SavedViewChatOut)
def update_saved_chat(chat_id: int, request: schemas.SavedViewChatUpdate, db: Session = Depends(get_db)):
    chat = db.get(models.SavedViewChat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Saved chat not found")
    chat.messages = _saved_chat_messages(request.messages)
    if request.title and request.title.strip():
        chat.title = " ".join(request.title.split())[:100]
    chat.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(chat)
    return chat


@router.delete("/views/chats/{chat_id}")
def delete_saved_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.get(models.SavedViewChat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Saved chat not found")
    db.delete(chat)
    db.commit()
    return {"deleted": True}
