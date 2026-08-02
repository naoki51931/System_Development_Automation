from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import create_database_engine, create_session_factory, session_scope
from app.models import EmailTemplate, MaintenancePlan, Role

SYSTEM_ROLES = {
    "organization_owner": "組織所有者",
    "organization_admin": "組織管理者",
    "project_manager": "プロジェクトマネージャー",
    "reviewer": "レビュアー",
    "developer": "開発者",
    "customer": "顧客",
    "viewer": "閲覧者",
}

MAINTENANCE_PLANS = {
    "light": ("Light", Decimal("10000.00000000"), 30, 0, 7, 24, False, False),
    "standard": ("Standard", Decimal("30000.00000000"), 120, 60, 30, 8, True, True),
    "premium": ("Premium", Decimal("80000.00000000"), 600, 240, 90, 2, True, True),
}

EMAIL_TEMPLATE_CODES = (
    "estimate_submitted", "estimate_approved", "contract_activated", "payment_succeeded",
    "payment_failed", "maintenance_past_due", "maintenance_suspended", "artifact_review_requested",
    "artifact_changes_requested", "artifact_approved", "deployment_completed",
    "resource_deletion_scheduled", "chat_message_received",
)


def seed_system_roles(session: Session) -> None:
    existing = set(session.scalars(select(Role.code).where(Role.code.in_(SYSTEM_ROLES))))
    session.add_all(
        Role(code=code, display_name=name, is_system=True)
        for code, name in SYSTEM_ROLES.items()
        if code not in existing
    )


def seed_maintenance_plans(session: Session) -> None:
    existing = set(session.scalars(select(MaintenancePlan.code).where(MaintenancePlan.organization_id.is_(None), MaintenancePlan.code.in_(MAINTENANCE_PLANS))))
    for code, (name, price, ai_minutes, human_minutes, retention, response, monitoring, staging) in MAINTENANCE_PLANS.items():
        if code not in existing:
            session.add(MaintenancePlan(
                organization_id=None, name=name, code=code, status="active", currency="JPY", monthly_price=price,
                included_ai_minutes=ai_minutes, included_human_minutes=human_minutes,
                backup_retention_days=retention, support_response_hours=response,
                monitoring_enabled=monitoring, staging_enabled=staging,

            ))


def seed_email_templates(session: Session) -> None:
    existing = set(session.scalars(select(EmailTemplate.template_code).where(
        EmailTemplate.organization_id.is_(None), EmailTemplate.locale == "ja",
        EmailTemplate.status == "approved", EmailTemplate.template_code.in_(EMAIL_TEMPLATE_CODES),
    )))
    for code in EMAIL_TEMPLATE_CODES:
        if code not in existing:
            session.add(EmailTemplate(
                organization_id=None, template_code=code,
                name=code.replace("_", " ").title(),
                subject_template="{{ service_name }}: {{ event_title }}",
                body_text_template="{{ user_name }} 様\n{{ event_body }}\n{{ action_url }}",
                body_html_template="<p>{{ user_name }} 様</p><p>{{ event_body }}</p><p>{{ action_url }}</p>",
                locale="ja", status="approved", version_number=1,
            ))


def main() -> None:
    engine = create_database_engine()
    factory = create_session_factory(engine)
    try:
        with session_scope(factory) as session:
            seed_system_roles(session)
            seed_maintenance_plans(session)
            seed_email_templates(session)
            session.commit()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
