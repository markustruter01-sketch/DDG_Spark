from __future__ import annotations

import hashlib
import hmac
import os

from sqlalchemy.engine import URL, make_url

# Database names keep the product's old name, Omni, on purpose. The login
# passwords are derived from these exact strings, so renaming them would change
# every password and every permission. Do not rename.
_SERVICE_ROLES = {"omni_platform", "omni_agent"}


def owner_url() -> URL:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required.")
    return make_url(value)


def derive_role_password(database_url: str | URL, role_name: str) -> str:
    """Derive a service login password from the owner's database password."""
    if role_name not in _SERVICE_ROLES:
        raise ValueError("Only the configured Spark service roles may be derived.")
    owner_password = make_url(database_url).password
    if not owner_password:
        raise RuntimeError(
            "DATABASE_URL must include the owner password to derive service logins."
        )
    message = f"omni-database-role:{role_name}".encode()
    return hmac.new(owner_password.encode(), message, hashlib.sha256).hexdigest()


def service_url(role_name: str) -> URL:
    if role_name not in _SERVICE_ROLES:
        raise ValueError("Only the configured Spark service roles may be connected.")
    url = owner_url()
    return url.set(
        username=role_name,
        password=derive_role_password(url, role_name),
    )
