"""JWT (HS256) — Sprint 6.

의존성 0 자체 구현. PyJWT 미설치 환경에서도 동작.
표준 JWT 와 동일한 wire format 이므로 다른 검증기로 교체 가능.

지원: HS256 (HMAC-SHA256). exp / iat / iss / sub claim 일치.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


class JWTError(Exception):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


@dataclass(frozen=True)
class JWTClaims:
    sub: str
    iss: str | None = None
    iat: int | None = None
    exp: int | None = None
    extra: dict[str, object] | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"sub": self.sub}
        if self.iss:
            payload["iss"] = self.iss
        if self.iat is not None:
            payload["iat"] = self.iat
        if self.exp is not None:
            payload["exp"] = self.exp
        if self.extra:
            payload.update(self.extra)
        return payload


def issue_token(
    *,
    secret: str,
    sub: str,
    iss: str | None = None,
    ttl_s: int = 3600,
    extra: dict[str, object] | None = None,
) -> str:
    if not secret:
        raise JWTError("secret must not be empty")
    now = int(time.time())
    claims = JWTClaims(sub=sub, iss=iss, iat=now, exp=now + ttl_s, extra=extra)
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p_b64 = _b64url_encode(json.dumps(claims.to_payload(), separators=(",", ":")).encode())
    msg = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    s_b64 = _b64url_encode(sig)
    return f"{h_b64}.{p_b64}.{s_b64}"


def verify_token(
    token: str,
    *,
    secret: str,
    iss: str | None = None,
    leeway_s: int = 30,
) -> dict[str, object]:
    if not token or token.count(".") != 2:
        raise JWTError("malformed token")
    h_b64, p_b64, s_b64 = token.split(".")
    msg = f"{h_b64}.{p_b64}".encode()
    expected = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    try:
        sig = _b64url_decode(s_b64)
    except Exception as exc:  # noqa: BLE001
        raise JWTError("invalid signature encoding") from exc
    if not hmac.compare_digest(sig, expected):
        raise JWTError("invalid signature")
    try:
        header = json.loads(_b64url_decode(h_b64))
        payload = json.loads(_b64url_decode(p_b64))
    except Exception as exc:  # noqa: BLE001
        raise JWTError("invalid payload") from exc
    if header.get("alg") != "HS256":
        raise JWTError("unsupported alg")

    now = int(time.time())
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and now > int(exp) + leeway_s:
        raise JWTError("token expired")
    if iss is not None and payload.get("iss") != iss:
        raise JWTError("issuer mismatch")
    return dict(payload)


__all__ = ["JWTError", "JWTClaims", "issue_token", "verify_token"]
