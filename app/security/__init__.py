"""Security layer — Sprint 6.

- ``guardrails``: PII 마스킹, 프롬프트 인젝션 탐지, 출력 sanitize
- ``audit``: append-only 감사 로그
- ``auth``: dev-token 기반 단순 인증 (운영 OAuth2 는 후속)
"""

from app.security.audit import AuditLog, audit_event, get_audit_log, set_audit_log
from app.security.auth import require_token
from app.security.guardrails import (
    GuardrailVerdict,
    classify_input,
    mask_pii,
    sanitize_text,
)

__all__ = [
    "AuditLog",
    "audit_event",
    "classify_input",
    "GuardrailVerdict",
    "get_audit_log",
    "mask_pii",
    "require_token",
    "sanitize_text",
    "set_audit_log",
]
