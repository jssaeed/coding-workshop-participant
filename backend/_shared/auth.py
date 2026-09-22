"""
Who is calling, and what are they allowed to do. Shared by every service.

How login works:
  1. At signup the password is hashed with bcrypt and only the hash is stored.
  2. At login the password is checked against the hash. If it matches, the
     user gets a token (a JWT) that contains their id and role, signed with
     a secret key so it cannot be forged.
  3. Every other request sends the token in the "Authorization: Bearer ..."
     header. current_user() checks the signature and reads the user out.

The signing secret comes from the JWT_SECRET environment variable, which
Terraform sets on every Lambda so they all accept each other's tokens.
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
ALL_ROLES = [ROLE_ADMIN, ROLE_ENGINEER, ROLE_EMPLOYEE]

# Roles that work on tickets (can be assigned, can change status).
STAFF_ROLES = [ROLE_ADMIN, ROLE_ENGINEER]

TOKEN_LIFETIME = timedelta(hours=12)

# Only used locally when JWT_SECRET is missing, so a fresh checkout just works.
LOCAL_DEV_SECRET = "local-dev-secret-not-for-cloud"


def get_secret():
    """The key used to sign tokens."""
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


# --- tokens ----------------------------------------------------------------

def create_token(user):
    """Make a signed token for a user row (needs id, email and role)."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),  # "subject": who the token is for
        "email": user["email"],
        "role": user["role"],
        "iat": now,  # issued at
        "exp": now + TOKEN_LIFETIME,  # expires
    }
    return jwt.encode(claims, get_secret(), algorithm="HS256")


def current_user(event):
    """
    Read the caller out of the Authorization header.

    Returns a dict with id, email and role. Raises 401 if there is no token
    or the token is invalid or expired.
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

    return {
        "id": int(claims["sub"]),
        "email": claims["email"],
        "role": claims["role"],
    }


# --- roles -----------------------------------------------------------------

def require_role(user, allowed_roles):
    """Raise 403 unless the user's role is in allowed_roles."""
    if user["role"] not in allowed_roles:
        raise HttpError(403, "Access denied")


def is_admin(user):
    return user["role"] == ROLE_ADMIN


def is_staff(user):
    return user["role"] in STAFF_ROLES
