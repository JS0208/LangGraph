from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import HTTPException

from app.security.jwt import JWTError, issue_token, verify_token


def test_issue_and_verify_round_trip():
    token = issue_token(secret="s3cret", sub="alice", iss="finrag", ttl_s=60)
    claims = verify_token(token, secret="s3cret", iss="finrag")
    assert claims["sub"] == "alice"
    assert claims["iss"] == "finrag"
    assert "iat" in claims and "exp" in claims


def test_verify_token_rejects_bad_signature():
    token = issue_token(secret="A", sub="x")
    with pytest.raises(JWTError):
        verify_token(token, secret="B")


def test_verify_token_rejects_malformed():
    with pytest.raises(JWTError):
        verify_token("not-a-token", secret="A")


def test_verify_token_rejects_issuer_mismatch():
    token = issue_token(secret="s", sub="x", iss="A")
    with pytest.raises(JWTError):
        verify_token(token, secret="s", iss="B")


def test_verify_token_rejects_expired():
    token = issue_token(secret="s", sub="x", ttl_s=-1)
    time.sleep(0.01)
    with pytest.raises(JWTError):
        verify_token(token, secret="s", leeway_s=0)


def test_verify_token_accepts_within_leeway():
    token = issue_token(secret="s", sub="x", ttl_s=-1)
    # leeway 5 sec → 통과
    assert verify_token(token, secret="s", leeway_s=5)["sub"] == "x"


def test_extra_claims_round_trip():
    token = issue_token(secret="s", sub="x", extra={"role": "admin", "scope": "read"})
    claims = verify_token(token, secret="s")
    assert claims["role"] == "admin"
    assert claims["scope"] == "read"


def test_require_token_jwt_accepts_valid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_AUTH_MODE", "jwt")
    monkeypatch.setenv("API_AUTH_JWT_SECRET", "topsecret")
    monkeypatch.setenv("API_AUTH_JWT_ISS", "fingraph")
    from app.security import auth

    token = issue_token(secret="topsecret", sub="bob", iss="fingraph", ttl_s=60)
    user = asyncio.run(auth.require_token(authorization=f"Bearer {token}"))
    assert user["mode"] == "jwt"
    assert user["actor"] == "bob"


def test_require_token_jwt_rejects_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_AUTH_MODE", "jwt")
    monkeypatch.setenv("API_AUTH_JWT_SECRET", "topsecret")
    from app.security import auth

    with pytest.raises(HTTPException):
        asyncio.run(auth.require_token(authorization="Bearer abc.def.ghi"))


def test_require_token_jwt_requires_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_AUTH_MODE", "jwt")
    monkeypatch.delenv("API_AUTH_JWT_SECRET", raising=False)
    from app.security import auth

    with pytest.raises(HTTPException):
        asyncio.run(auth.require_token(authorization="Bearer x.y.z"))
