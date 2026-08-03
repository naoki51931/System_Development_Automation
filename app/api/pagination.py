import base64, hashlib, hmac, json, os, uuid
from datetime import datetime
from fastapi import HTTPException

MAX_PAGE_SIZE = 100

def encode_cursor(created_at: datetime, item_id: uuid.UUID) -> str:
    raw = json.dumps({"created_at": created_at.isoformat(), "id": str(item_id)}, separators=(",", ":")).encode()
    sig = hmac.new(os.getenv("APP_CURSOR_SECRET", "local-cursor-secret").encode(), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + sig).decode().rstrip("=")

def decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        blob = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)); raw, sig = blob[:-32], blob[-32:]
        expected = hmac.new(os.getenv("APP_CURSOR_SECRET", "local-cursor-secret").encode(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected): raise ValueError
        data = json.loads(raw); return datetime.fromisoformat(data["created_at"]), uuid.UUID(data["id"])
    except Exception as exc:
        raise HTTPException(400, detail={"code": "INVALID_CURSOR", "message": "Cursor is invalid"}) from exc

def page(values, size: int, serializer):
    items = list(values); has_more = len(items) > size; items = items[:size]
    return {"items": [serializer(x) for x in items], "next_cursor": encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None}

def paginate_query(session, statement, model, cursor: str | None, size: int, serializer):
    from sqlalchemy import and_, or_
    size = max(1, min(size, MAX_PAGE_SIZE))
    if cursor:
        created_at, item_id = decode_cursor(cursor)
        statement = statement.where(or_(model.created_at < created_at, and_(model.created_at == created_at, model.id < item_id)))
    values = session.scalars(statement.order_by(model.created_at.desc(), model.id.desc()).limit(size + 1)).all()
    return page(values, size, serializer)
