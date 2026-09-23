"""
Who is calling, and what are they allowed to do. Shared by every service.

How login works:
  1. At signup the password is hashed with bcrypt and only the hash is stored.
  2. At login the password is checked against the hash. If it matches, the
     user gets two tokens:
       - an ACCESS token: a JWT with the user's id and role, signed with a
         secret key so it cannot be forged. Short-lived (15 minutes). Sent
         on every request in the "Authorization: Bearer ..." header.
       - a REFRESH token: a long random string (14 days). Sent only to
         POST /users/refresh to get a new access token when the old one
         expires. Stored hashed in the refresh_tokens table so it can be
         revoked (logout, demotion).
  3. current_user() checks the access token's signature to learn WHO is
     calling, then reads the user's CURRENT role from the database. The role
     inside the token is a hint for the frontend; permission decisions use
     the database, so a role change takes effect on the very next request.

The signing secret comes from the JWT_SECRET environment variable, which
Terraform sets on every Lambda so they all accept each other's tokens.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .database import fetch_one
from .request import headers
from .responses import HttpError

logger = logging.getLogger()

IS_LOCAL = os.getenv("IS_LOCAL", "false") == "true"

ROLE_ADMIN = "facility_admin"
ROLE_ENGINEER = "engineer"
ROLE_EMPLOYEE = "employee"
ALL_ROLES = [ROLE_ADMIN, ROLE_ENGINEER, ROLE_EMPLOYEE]

# Roles that work on tickets (can be assigned, can change status).
STAFF_ROLES = [ROLE_ADMIN, ROLE_ENGINEER]

# Higher number = more power. Used to tell a promotion from a demotion.
ROLE_RANK = {ROLE_EMPLOYEE: 0, ROLE_ENGINEER: 1, ROLE_ADMIN: 2}

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME = timedelta(days=14)

# Only used locally when JWT_SECRET is missing, so a fresh checkout just works.
LOCAL_DEV_SECRET = "local-dev-secret-not-for-cloud"


def get_secret():
    """The key used to sign access tokens."""
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret:
        return secret
    if IS_LOCAL:
        logger.warning("JWT_SECRET is not set; using the local development secret")
        return LOCAL_DEV_SECRET
    # In the cloud a missing secret must be an error: signing tokens with a
    # known constant would let anyone create an admin token.
    raise HttpError(500, "Server authentication is not configured")


# --- passwords -------------------------------------------------------------

def hash_password(password):
    """Turn a password into a hash that is safe to store."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    """True if the password matches the stored hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False  # the stored hash is damaged; treat as no match


# --- access tokens (JWT) ---------------------------------------------------

def create_access_token(user):
    """Make a signed, short-lived token for a user row (needs id, email, role)."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),  # "subject": who the token is for
        "email": user["email"],
        "role": user["role"],
        "iat": now,  # issued at
        "exp": now + ACCESS_TOKEN_LIFETIME,  # expires
    }
    return jwt.encode(claims, get_secret(), algorithm="HS256")


def current_user(event):
    """
    Identify the caller and load their current role.

    Step 1: the Authorization header must carry a valid, unexpired access
            token. That proves WHO is calling.
    Step 2: the user's role is read from the database, not from the token,
            so a promotion or demotion applies immediately. A missing row
            means the account was deleted.

    Returns a dict with id, email, role and branch_id. Raises 401 on any
    failure.
    """
    authorization = headers(event).get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HttpError(401, "Authentication required")

    token = authorization[len("bearer "):].strip()
    try:
        claims = jwt.decode(token, get_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HttpError(401, "Token has expired")
    except jwt.InvalidTokenError:
        raise HttpError(401, "Token is invalid")

    user = fetch_one(
        "SELECT id, email, role, branch_id FROM users WHERE id = %s",
        (int(claims["sub"]),),
    )
    if user is None:
        raise HttpError(401, "Account no longer exists")

    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "branch_id": user["branch_id"],
    }


# --- refresh tokens --------------------------------------------------------

def create_refresh_token():
    """
    Make a new refresh token.

    Returns (token, token_hash, expires_at). The token goes to the client;
    only the hash is stored, the same way passwords are handled.
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + REFRESH_TOKEN_LIFETIME
    return token, hash_refresh_token(token), expires_at


def hash_refresh_token(token):
    """SHA-256 of a refresh token, for storing and looking it up."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- roles -----------------------------------------------------------------

def require_role(user, allowed_roles):
    """Raise 403 unless the user's role is in allowed_roles."""
    if user["role"] not in allowed_roles:
        raise HttpError(403, "Access denied")


def is_admin(user):
    return user["role"] == ROLE_ADMIN


def is_staff(user):
    return user["role"] in STAFF_ROLES


def is_demotion(old_role, new_role):
    """True when the change takes power away (used to revoke refresh tokens)."""
    return ROLE_RANK[new_role] < ROLE_RANK[old_role]
