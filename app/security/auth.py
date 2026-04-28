"""인증 — Sprint 6.

지원 모드 (``API_AUTH_MODE``)
- ``disabled`` (기본): 모든 호출 통과 — 데모/로컬 호환
- ``token``: ``API_AUTH_TOKENS`` 화이트리스트 (콤마 구분) 와 비교
- ``jwt``: ``API_AUTH_JWT_SECRET`` HS256 키로 검증, 선택적으로 ``API_AUTH_JWT_ISS`` 에 issuer 일치 검증

토큰은 ``Authorization: Bearer <token>`` 또는 평문 ``Authorization: <token>`` 모두 수용.
모든 인증 결과는 ``audit_event`` 에 기록된다.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Header, HTTPException, status

from app.security.audit import audit_event
from app.security.jwt import JWTError, verify_token


def _allowed_tokens() -> set[str]:
    raw = os.getenv("API_AUTH_TOKENS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _auth_mode() -> str:
    return (os.getenv("API_AUTH_MODE") or "disabled").strip().lower()


def _extract_bearer(header: str | None) -> str:
    if not header:
        return ""
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return header.strip()


async def require_token(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    mode = _auth_mode()
    if mode in {"disabled", "off", ""}:
        return {"actor": "anonymous", "mode": "disabled"}

    presented = _extract_bearer(authorization)

    if mode == "token":
        allowed = _allowed_tokens()
        if not presented or presented not in allowed:
            audit_event("auth.denied", actor=None, result="fail", meta={"mode": mode, "presented": bool(presented)})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing token")
        actor = presented[:6] + "…"
        audit_event("auth.granted", actor=actor, result="ok", meta={"mode": mode})
        return {"actor": actor, "mode": mode}

    if mode == "jwt":
        secret = os.getenv("API_AUTH_JWT_SECRET", "")
        if not secret:
            audit_event("auth.misconfigured", result="fail", meta={"mode": mode})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWT secret not configured")
        if not presented:
            audit_event("auth.denied", actor=None, result="fail", meta={"mode": mode, "presented": False})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
        try:
            claims = verify_token(presented, secret=secret, iss=os.getenv("API_AUTH_JWT_ISS") or None)
        except JWTError as exc:
            audit_event("auth.denied", actor=None, result="fail", meta={"mode": mode, "reason": str(exc)})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"jwt invalid: {exc}") from exc
        actor = str(claims.get("sub") or "jwt-user")
        audit_event("auth.granted", actor=actor, result="ok", meta={"mode": mode, "iss": claims.get("iss")})
        return {"actor": actor, "mode": mode, "claims": claims}

    audit_event("auth.invalid_mode", actor=None, result="fail", meta={"mode": mode})
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="invalid auth mode")


__all__ = ["require_token"]
