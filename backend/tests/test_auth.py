from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from starlette.requests import Request

from omni.api import auth
from omni.config import Settings, get_settings


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
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.committed = False

    def execute(
        self,
        statement: Any,
        parameters: dict[str, Any] | None = None,
    ) -> FakeResult:
        self.calls.append((str(statement), parameters or {}))
        return FakeResult(self.user)

    def commit(self) -> None:
        self.committed = True


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
    def fake_platform_session():
        yield FakeSession(user)

    monkeypatch.setattr(auth, "platform_session", fake_platform_session)
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
    def fake_platform_session():
        yield FakeSession(user)

    monkeypatch.setattr(auth, "platform_session", fake_platform_session)
    with pytest.raises(HTTPException) as error:
        auth.sign_in(
            auth.SignInRequest(email=user["email"], password="incorrect-password"),
            make_request(),
            Response(),
        )
    assert error.value.status_code == 401


def test_session_secret_has_no_builtin_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://owner:example@localhost/omni")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET is required"):
        get_settings()


def test_admin_password_secret_updates_existing_hash_without_logging(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    new_password = "secret-only-test-value"
    old_hash = auth.password_hasher.hash("old-test-password")
    session = FakeSession({"id": "7410cfa0-ef17-4b3f-9c5d-cced479c30aa"})
    settings = Settings(
        database_url="postgresql://owner:example@localhost/omni",
        session_secret="test-session-secret",
        admin_email="admin@omni.local",
        admin_password=new_password,
    )

    @contextmanager
    def fake_platform_session():
        yield session

    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "platform_session", fake_platform_session)
    auth.ensure_admin_account()

    updates = [
        parameters
        for statement, parameters in session.calls
        if statement.lstrip().startswith("UPDATE auth_user")
    ]
    assert len(updates) == 1
    new_hash = updates[0]["password_hash"]
    assert isinstance(new_hash, str)
    assert new_hash != old_hash
    assert new_hash != new_password
    assert auth.password_hasher.verify(new_hash, new_password)
    assert session.committed
    assert new_password not in caplog.text


def test_admin_password_is_unchanged_when_secret_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession({"id": "7410cfa0-ef17-4b3f-9c5d-cced479c30aa"})
    settings = Settings(
        database_url="postgresql://owner:example@localhost/omni",
        session_secret="test-session-secret",
        admin_email="admin@omni.local",
        admin_password=None,
    )

    @contextmanager
    def fake_platform_session():
        yield session

    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "platform_session", fake_platform_session)
    auth.ensure_admin_account()

    assert not any(
        statement.lstrip().startswith("UPDATE auth_user")
        for statement, _ in session.calls
    )
    assert not session.committed


def test_sign_out_route_requires_a_session_and_clears_the_cookie() -> None:
    app = FastAPI()
    app.include_router(auth.router)
    with TestClient(app) as client:
        assert client.post("/api/auth/sign-out").status_code == 401
        app.dependency_overrides[auth.require_session] = lambda: {
            "user_id": "7410cfa0-ef17-4b3f-9c5d-cced479c30aa",
            "email": "admin@omni.local",
            "role": "administrator",
            "clearance": "restricted",
        }
        response = client.post("/api/auth/sign-out")
    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert auth.COOKIE_NAME in cookie
    assert "max-age=0" in cookie
    assert "httponly" in cookie


def test_sign_out_helper_deletes_the_session_cookie() -> None:
    response = Response()
    auth.sign_out(
        {"user_id": "7410cfa0-ef17-4b3f-9c5d-cced479c30aa"},
        make_request(),
        response,
    )
    cookie = response.headers["set-cookie"].lower()
    assert auth.COOKIE_NAME in cookie
    assert "max-age=0" in cookie
    assert "httponly" in cookie
