from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2 import exceptions as argon_exceptions
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from spark.config import dev_skip_sign_in, get_settings
from spark.db.platform import platform_session

logger = logging.getLogger("spark.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])
password_hasher = PasswordHasher()
COOKIE_NAME = "spark_session"
SESSION_TTL_SECONDS = 12 * 60 * 60


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class SessionResponse(BaseModel):
    user_id: str
    email: str
    role: str
    clearance: str


def _encode_session(user_id: str, secret: str, expires_at: int) -> str:
    payload = json.dumps(
        {"sub": user_id, "exp": expires_at}, separators=(",", ":")
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    signed = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{encoded}.{signed}"


def _decode_session(token: str, secret: str) -> dict[str, Any] | None:
    try:
        encoded, signature = token.split(".", maxsplit=1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            return None
        payload_bytes = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        raw_payload: object = json.loads(payload_bytes)
        if not isinstance(raw_payload, dict):
            return None
        payload = cast(dict[str, Any], raw_payload)
        if int(payload["exp"]) < int(time.time()):
            return None
        UUID(str(payload["sub"]))
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def ensure_admin_account() -> None:
    settings = get_settings()
    with platform_session() as session:
        # Database-side name; keeps the old product name like the other
        # database names (see db/credentials.py).
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('omni-admin-bootstrap'))")
        )
        found = session.execute(
            text("SELECT 1 FROM auth_user WHERE role = 'administrator' LIMIT 1")
        ).first()
        if found:
            if settings.admin_password is not None:
                password_hash = password_hasher.hash(settings.admin_password)
                session.execute(
                    text(
                        """
                        UPDATE auth_user SET password_hash = :password_hash
                        WHERE role = 'administrator'
                        """
                    ),
                    {"password_hash": password_hash},
                )
                session.commit()
            return

    generated = settings.admin_password is None
    password = settings.admin_password or secrets.token_urlsafe(24)
    password_hash = password_hasher.hash(password)
    with platform_session() as session:
        created = session.execute(
            text(
                """
                INSERT INTO auth_user
                  (id, email, password_hash, role, clearance, created_at)
                SELECT :id, :email, :password_hash, 'administrator',
                       'restricted', now()
                WHERE NOT EXISTS (
                  SELECT 1 FROM auth_user WHERE role = 'administrator'
                )
                ON CONFLICT DO NOTHING
                RETURNING id
                """
            ),
            {
                "id": uuid4(),
                "email": settings.admin_email.lower(),
                "password_hash": password_hash,
            },
        ).scalar_one_or_none()
        session.commit()
    if created is not None and generated:
        logger.warning(
            "Generated initial administrator password (shown once): %s",
            password,
        )
    elif created is not None:
        logger.info("Created the configured administrator account.")


def _dev_administrator() -> dict[str, Any]:
    with platform_session() as session:
        user = (
            session.execute(
                text(
                    """
                SELECT id::text AS user_id, email, role, clearance
                FROM auth_user WHERE role = 'administrator'
                ORDER BY created_at LIMIT 1
                """
                )
            )
            .mappings()
            .first()
        )
    if user is None:
        raise HTTPException(status_code=401, detail="No administrator exists yet.")
    return dict(user)


def require_session(request: Request) -> dict[str, Any]:
    if dev_skip_sign_in():
        return _dev_administrator()
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Sign-in required.")
    payload = _decode_session(token, get_settings().session_secret)
    if not payload:
        raise HTTPException(status_code=401, detail="Session is invalid or expired.")
    with platform_session() as session:
        user = (
            session.execute(
                text(
                    """
                SELECT id::text AS user_id, email, role, clearance
                FROM auth_user WHERE id = :user_id
                """
                ),
                {"user_id": payload["sub"]},
            )
            .mappings()
            .first()
        )
    if user is None:
        raise HTTPException(status_code=401, detail="Session user was not found.")
    return dict(user)


CurrentUser = Annotated[dict[str, Any], Depends(require_session)]


@router.post("/sign-in", response_model=SessionResponse)
def sign_in(
    body: SignInRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    with platform_session() as session:
        user = (
            session.execute(
                text(
                    """
                SELECT id::text AS user_id, email, password_hash, role, clearance
                FROM auth_user WHERE email = :email
                """
                ),
                {"email": body.email.strip().lower()},
            )
            .mappings()
            .first()
        )
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    try:
        password_hasher.verify(user["password_hash"], body.password)
    except (argon_exceptions.VerifyMismatchError, argon_exceptions.InvalidHashError):
        raise HTTPException(
            status_code=401, detail="Email or password is incorrect."
        ) from None
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    response.set_cookie(
        COOKIE_NAME,
        _encode_session(user["user_id"], get_settings().session_secret, expires_at),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return SessionResponse(
        user_id=user["user_id"],
        email=user["email"],
        role=user["role"],
        clearance=user["clearance"],
    )


@router.get("/session", response_model=SessionResponse)
def session_info(user: CurrentUser) -> SessionResponse:
    return SessionResponse(**user)


@router.post("/sign-out", status_code=204)
def sign_out(
    _: CurrentUser,
    request: Request,
    response: Response,
) -> Response:
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )
    response.status_code = 204
    return response
