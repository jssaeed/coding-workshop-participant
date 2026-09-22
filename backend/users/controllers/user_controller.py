"""
User controller: account creation, login, role changes and deletion.

Holds the access rules for accounts. Self-service signup always produces an
employee; only a facility admin may change roles or delete accounts.
"""

import logging

from lib import auth, validation
from lib.request import json_body, query_params
from lib.responses import HttpError, created, no_content, ok
from models import user as user_model
from views import user_view

logger = logging.getLogger()

# Roles an admin may assign. Self-service signup cannot reach this path.
ASSIGNABLE_ROLES = (auth.ROLE_EMPLOYEE, auth.ROLE_ENGINEER, auth.ROLE_ADMIN)

def create_account(event):
    """
    Register a new account. Public, and always creates an employee.

    Returns 201 with the new user, or 409 when the email is taken.
    """
    body = json_body(event)
    email = validation.email(body)
    password = validation.password(body)
    name = validation.required_string(body, "name", max_length=255)

    # Checked up front for a clear message; the unique index is what actually
    # guarantees it under concurrent signups.
    if user_model.email_taken(email):
        raise HttpError(409, "An account with that email already exists")

    row = user_model.create(
        email=email,
        password_hash=auth.hash_password(password),
        name=name,
        # Never read the role from the request: that would let anyone sign up
        # as an admin.
        role=auth.ROLE_EMPLOYEE,
    )
    logger.info("Created account %s", row["id"])
    return created(user_view.serialize(row))

def login(event):
    """
    Exchange email and password for an access token.

    Returns 200 with a token, or 401 when the credentials do not match.
    """
    body = json_body(event)
    email = validation.email(body)
    password = body.get("password")

    if not isinstance(password, str) or not password:
        raise HttpError(400, "'password' is required")

    row = user_model.find_by_email_with_hash(email)

    # One message for both unknown email and wrong password, so the response
    # cannot be used to discover which accounts exist.
    if row is None or not auth.verify_password(password, row["password_hash"]):
        raise HttpError(401, "Email or password is incorrect")

    token = auth.create_token(row)
    return ok(user_view.with_token(row, token))

def me(event):
    """Return the signed-in user's own account."""
    caller = auth.current_user(event)
    row = user_model.find_by_id(caller["id"])
    if row is None:
        # The token is validly signed but the account is gone.
        raise HttpError(401, "Account no longer exists")
    return ok(user_view.serialize(row))

def list_users(event):
    """
    List accounts. Admin only, since it exposes every user.

    Supports ?role= to filter, which the assign-ticket UI uses to list
    engineers.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, auth.ROLE_ADMIN)

    role = query_params(event).get("role")
    if role and role not in auth.ROLES:
        raise HttpError(400, f"'role' must be one of: {', '.join(sorted(auth.ROLES))}")

    return ok(user_view.serialize_many(user_model.list_all(role)))

def update_role(event, user_id):
    """
    Promote or demote an account. Admin only.

    Returns 200 with the updated user, 404 when absent, or 403 when an admin
    targets their own account.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, auth.ROLE_ADMIN)

    body = json_body(event)
    role = validation.one_of(body, "role", ASSIGNABLE_ROLES)

    # Without this an admin could demote themselves and leave the system with
    # no one able to manage roles.
    if user_id == caller["id"]:
        raise HttpError(403, "You cannot change your own role")

    row = user_model.update_role(user_id, role)
    if row is None:
        raise HttpError(404, "User not found")

    logger.info("User %s role changed to %s by %s", user_id, role, caller["id"])
    return ok(user_view.serialize(row))

def delete_user(event, user_id):
    """
    Delete an account. Admin only.

    Returns 204, 404 when absent, or 409 when the user still has incidents,
    which the reported_by foreign key refuses to orphan.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, auth.ROLE_ADMIN)

    if user_id == caller["id"]:
        raise HttpError(403, "You cannot delete your own account")

    try:
        deleted = user_model.delete(user_id)
    except user_model.UserInUse as exc:
        raise HttpError(
            409, "User has incidents or messages and cannot be deleted"
        ) from exc

    if not deleted:
        raise HttpError(404, "User not found")

    logger.info("User %s deleted by %s", user_id, caller["id"])
    return no_content()
