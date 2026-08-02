from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import create_database_engine, create_session_factory, session_scope
from app.models import Role

SYSTEM_ROLES = {
    "organization_owner": "組織所有者",
    "organization_admin": "組織管理者",
    "project_manager": "プロジェクトマネージャー",
    "reviewer": "レビュアー",
    "developer": "開発者",
    "customer": "顧客",
    "viewer": "閲覧者",
}


def seed_system_roles(session: Session) -> None:
    existing = set(session.scalars(select(Role.code).where(Role.code.in_(SYSTEM_ROLES))))
    session.add_all(
        Role(code=code, display_name=name, is_system=True)
        for code, name in SYSTEM_ROLES.items()
        if code not in existing
    )


def main() -> None:
    engine = create_database_engine()
    factory = create_session_factory(engine)
    try:
        with session_scope(factory) as session:
            seed_system_roles(session)
            session.commit()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
