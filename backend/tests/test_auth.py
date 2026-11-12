from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from omni.api import auth


class FakeResult:
    def __init__(self, user: dict[str, Any] | None) -> None:
        self.user = user

    def mappings(self) -> FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self.user


class FakeSession:
    def __init__(self, user: dict[str, Any] | None) -> None:
        self.user = user

    def execute(self, *_: Any, **__: Any) -> FakeResult:
        return FakeResult(self.user)


def make_request(scheme: str = "https") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": scheme,
            "path": "/api/auth/sign-in",
            "raw_path": b"/api/auth/sign-in",
            "query_string": b"",
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 443),
        }
    )


def test_sign_in_uses_argon2_and_sets_signed_session_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "test-only-password"
    user = {
        "user_id": "7410cfa0-ef17-4b3f-9c5d-cced479c30aa",
        "email": "admin@omni.local",
        "password_hash": auth.password_hasher.hash(password),
        "role": "administrator",
        "clearance": "restricted",
    }

    @contextmanager
    def fake_reader_session():
        yield FakeSession(user)

    monkeypatch.setattr(auth, "reader_session", fake_reader_session)
    response = Response()
    signed_in = auth.sign_in(
        auth.SignInRequest(email=user["email"], password=password),
        make_request(),
        response,
    )

    assert signed_in.role == "administrator"
    assert "$argon2id$" in user["password_hash"]
    cookie = response.headers["set-cookie"]
    token = cookie.split(";", maxsplit=1)[0].split("=", maxsplit=1)[1]
    assert "httponly" in cookie.lower()
    assert "secure" in cookie.lower()
    assert auth._decode_session(token, auth.get_settings().session_secret) is not None


def test_sign_in_rejects_an_incorrect_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = {
        "user_id": "7410cfa0-ef17-4b3f-9c5d-cced479c30aa",
        "email": "admin@omni.local",
        "password_hash": auth.password_hasher.hash("correct-password"),
        "role": "administrator",
        "clearance": "restricted",
    }

    @contextmanager
    def fake_reader_session():
        yield FakeSession(user)

    monkeypatch.setattr(auth, "reader_session", fake_reader_session)
    with pytest.raises(HTTPException) as error:
        auth.sign_in(
            auth.SignInRequest(email=user["email"], password="incorrect-password"),
            make_request(),
            Response(),
        )
    assert error.value.status_code == 401
