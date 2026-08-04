import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import HTTPException

MAX_PAGE_SIZE = 100
DEFAULT_CURSOR_TTL_SECONDS = 3600


def encode_cursor(
    created_at: datetime,
    item_id: uuid.UUID,
    *,
    scope: str | None = None,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(timezone.utc)
    raw = json.dumps(
        {
            "created_at": created_at.isoformat(),
            "id": str(item_id),
            "issued_at": issued_at.isoformat(),
            "scope": scope,
            "sort": "created_at_desc_id_desc",
        },
        separators=(",", ":"),
    ).encode()
    sig = hmac.new(
        os.getenv("APP_CURSOR_SECRET", "local-cursor-secret").encode(),
        raw,
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(raw + sig).decode().rstrip("=")


def decode_cursor(
    value: str,
    *,
    expected_scope: str | None = None,
    now: datetime | None = None,
    ttl_seconds: int = DEFAULT_CURSOR_TTL_SECONDS,
) -> tuple[datetime, uuid.UUID]:
    try:
        blob = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        raw, sig = blob[:-32], blob[-32:]
        expected = hmac.new(
            os.getenv("APP_CURSOR_SECRET", "local-cursor-secret").encode(),
            raw,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("invalid cursor signature")
        data = json.loads(raw)
        if data.get("sort") != "created_at_desc_id_desc":
            raise ValueError("unsupported cursor sort")
        if expected_scope is not None and data.get("scope") != expected_scope:
            raise ValueError("cursor scope mismatch")
        issued_at = datetime.fromisoformat(data["issued_at"])
        current_time = now or datetime.now(timezone.utc)
        if issued_at.tzinfo is None or current_time > issued_at + timedelta(
            seconds=ttl_seconds
        ):
            raise ValueError("cursor expired")
        return datetime.fromisoformat(data["created_at"]), uuid.UUID(data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            400, detail={"code": "INVALID_CURSOR", "message": "Cursor is invalid"}
        ) from exc


def page(
    values: list[Any],
    size: int,
    serializer: Callable[[Any], dict[str, object]],
    *,
    scope: str | None = None,
) -> dict[str, object]:
    items = list(values)
    has_more = len(items) > size
    items = items[:size]
    return {
        "items": [serializer(x) for x in items],
        "next_cursor": encode_cursor(items[-1].created_at, items[-1].id, scope=scope)
        if has_more and items
        else None,
    }


def paginate_query(
    session,
    statement,
    model,
    cursor: str | None,
    size: int,
    serializer: Callable[[Any], dict[str, object]],
    *,
    scope: str | None = None,
):
    from sqlalchemy import and_, or_

    size = max(1, min(size, MAX_PAGE_SIZE))
    if cursor:
        created_at, item_id = decode_cursor(cursor, expected_scope=scope)
        statement = statement.where(
            or_(
                model.created_at < created_at,
                and_(model.created_at == created_at, model.id < item_id),
            )
        )
    values = session.scalars(
        statement.order_by(model.created_at.desc(), model.id.desc()).limit(size + 1)
    ).all()
    return page(values, size, serializer, scope=scope)
