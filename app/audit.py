import uuid
import ipaddress
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "client_secret",
    "id_token",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def sanitize_audit_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if str(key).lower() in SENSITIVE_KEYS
            else sanitize_audit_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_audit_value(item) for item in value]
    return value


def record_audit_log(
    session: Session,
    *,
    organization_id: uuid.UUID,
    action: str,
    resource_type: str,
    request_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    ip_address: str | None = None,
    actor_type: str = "human",
    approval_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
    result: str | None = None,
    reason: str | None = None,
) -> AuditLog:
    normalized_ip = None
    if ip_address is not None:
        try:
            normalized_ip = str(ipaddress.ip_address(ip_address))
        except ValueError:
            # Test clients/proxies can provide a non-IP peer label; never let
            # an invalid value abort the security event itself.
            normalized_ip = None
    log = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        before_json=sanitize_audit_value(before) if before is not None else None,
        after_json=sanitize_audit_value(after) if after is not None else None,
        ip_address=normalized_ip,
        actor_type=actor_type,
        approval_id=approval_id,
        correlation_id=correlation_id,
        result=result,
        reason=reason,
    )
    session.add(log)
    return log
