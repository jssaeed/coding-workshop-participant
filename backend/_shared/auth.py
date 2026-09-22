"""
Authentication and role-based access control shared by every service.

Authentication first (who is calling, proven by a signed token), authorization
second (may that role do this). Both checks live here so no service invents its
own rules.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .request import headers
from .responses import HttpError

logger = logging.getLogger()

IS_LOCAL = os.getenv("IS_LOCAL", "false") == "true"

ROLE_ADMIN = "facility_admin"
ROLE_ENGINEER = "engineer"
ROLE_EMPLOYEE = "employee"
ROLES = (ROLE_ADMIN, ROLE_ENGINEER, ROLE_EMPLOYEE)

# Roles that may work on other people's tickets.
STAFF_ROLES = (ROLE_ADMIN, ROLE_ENGINEER)

JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 12

# Used only when JWT_SECRET is missing locally, so a fresh checkout runs
# without setup. In the cloud a missing secret is a hard error instead: signing
# tokens with a public constant would let anyone mint an admin token.
_LOCAL_DEV_SECRET = "local-dev-secret-not-for-cloud"

def _secret():
    """Return the token signing secret, or fail loudly in the cloud."""
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret:
        return secret
    if IS_LOCAL:
        logger.warning("JWT_SECRET is not set - using the local development secret")
        return _LOCAL_DEV_SECRET
    raise HttpError(500, "Server authentication is not configured")

def hash_password(plain_password):
    """Hash a password for storage. Never store the password itself."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password, password_hash):
    """Check a password against its stored hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        # A malformed or truncated hash in the database, not a valid login.
        return False

def create_token(user):
    """
    Sign a token identifying a user.

    Args:
        user (dict): a row with id, email and role

    Returns:
        str: the encoded JWT
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)

def decode_token(token):
    """
    Verify a token's signature and expiry.

    Raises:
        HttpError: 401 when the token is expired or invalid
    """
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HttpError(401, "Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HttpError(401, "Token is invalid") from exc

def current_user(event):
    """
    Identify the caller from the Authorization header.

    Returns:
        dict: id, email and role of the caller

    Raises:
        HttpError: 401 when the header is missing or the token does not verify
    """
    authorization = headers(event).get("authorization", "")
    prefix = "bearer "
    if not authorization.lower().startswith(prefix):
        raise HttpError(401, "Authentication required")

    claims = decode_token(authorization[len(prefix):].strip())
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HttpError(401, "Token is invalid") from exc

    return {
        "id": user_id,
        "email": claims.get("email"),
        "role": claims.get("role"),
    }

def require_role(user, *allowed_roles):
    """
    Stop the request unless the caller holds one of the given roles.

    Raises:
        HttpError: 403 with a consistent access-denied message
    """
    if user.get("role") not in allowed_roles:
        raise HttpError(403, "Access denied")
    return user

def is_admin(user):
    """True when the caller is a facility admin."""
    return user.get("role") == ROLE_ADMIN

def is_staff(user):
    """True when the caller is an engineer or a facility admin."""
    return user.get("role") in STAFF_ROLES
