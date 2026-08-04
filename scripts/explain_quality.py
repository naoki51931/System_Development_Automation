import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db.session import create_database_engine

QUERIES = {
    "projects": "SELECT * FROM projects WHERE organization_id=(SELECT organization_id FROM projects GROUP BY organization_id ORDER BY count(*) DESC LIMIT 1) AND archived_at IS NULL ORDER BY created_at DESC,id DESC LIMIT 51",
    "notifications": "SELECT * FROM notifications WHERE organization_id=(SELECT organization_id FROM notifications GROUP BY organization_id ORDER BY count(*) DESC LIMIT 1) ORDER BY created_at DESC,id DESC LIMIT 51",
    "chat_messages": "SELECT * FROM chat_messages WHERE organization_id=(SELECT organization_id FROM chat_messages GROUP BY organization_id ORDER BY count(*) DESC LIMIT 1) AND chat_room_id=(SELECT chat_room_id FROM chat_messages GROUP BY chat_room_id ORDER BY count(*) DESC LIMIT 1) ORDER BY created_at DESC,id DESC LIMIT 51",
    "audit_logs": "SELECT * FROM audit_logs WHERE organization_id=(SELECT organization_id FROM audit_logs GROUP BY organization_id ORDER BY count(*) DESC LIMIT 1) ORDER BY created_at DESC,id DESC LIMIT 51",
    "reviews": "SELECT * FROM reviews WHERE organization_id=(SELECT organization_id FROM reviews LIMIT 1) ORDER BY created_at DESC,id DESC LIMIT 51",
    "outbox_claim": "SELECT * FROM outbox_events WHERE status IN ('queued','retry_wait') AND available_at<=now() ORDER BY available_at,created_at,id FOR UPDATE SKIP LOCKED LIMIT 1",
    "dead_letters": "SELECT * FROM outbox_events WHERE organization_id=(SELECT organization_id FROM outbox_events LIMIT 1) AND status='dead_letter' ORDER BY created_at DESC,id DESC LIMIT 51",
}


def main():
    result = {}
    with create_database_engine().connect() as c:
        for name, query in QUERIES.items():
            result[name] = c.execute(
                text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + query)
            ).scalar()
    Path("quality-results/db-explain.json").write_text(
        json.dumps(result, indent=2, default=str) + "\n"
    )


if __name__ == "__main__":
    main()
