"""
User controller: the rules for accounts.

- Anyone with a company email (ending in @acme.inc) can create an account;
  it is always an employee.
- Anyone can log in.
- Only an admin can list users, change roles, or delete accounts.
- An admin cannot change or delete their own account (so the system can
  never end up with no admin).
"""

import logging

from lib import auth, validation
from lib.request import json_body, query_params
from lib.responses import HttpError, created, no_content, ok
from models import user as user_model
from views import user_view

logger = logging.getLogger()

# Only company addresses may sign up. Compared after lower-casing, so
# Ana@ACME.INC is accepted.
COMPANY_EMAIL_DOMAIN = "@acme.inc"


def create_account(event):
    """POST /api/users - sign up. Always creates an employee."""
    body = json_body(event)
    email = validation.email(body)
    password = validation.password(body)
    name = validation.required_string(body, "name", max_length=255)

    # Business rule: accounts are for company staff only.
    if not email.endswith(COMPANY_EMAIL_DOMAIN):
        raise HttpError(400, f"'email' must be a company address ending in {COMPANY_EMAIL_DOMAIN}")

    if user_model.email_exists(email):
        raise HttpError(409, "An account with that email already exists")

    # The role is fixed here, not read from the request. Otherwise anyone
    # could sign up as an admin.
    user = user_model.create(
        email=email,
        password_hash=auth.hash_password(password),
        name=name,
        role=auth.ROLE_EMPLOYEE,
    )
    logger.info("Created account %s", user["id"])
    return created(user_view.serialize(user))


def login(event):
    """POST /api/users/login - check the password and hand out a token."""
    body = json_body(event)
    email = validation.email(body)
    password = body.get("password")
    if not isinstance(password, str) or password == "":
        raise HttpError(400, "'password' is required")

    user = user_model.find_by_email_for_login(email)

    # Same message whether the email is unknown or the password is wrong, so
    # the login form cannot be used to find out which emails have accounts.
    if user is None or not auth.check_password(password, user["password_hash"]):
        raise HttpError(401, "Email or password is incorrect")

    return ok({
        "user": user_view.serialize(user),
        "token": auth.create_token(user),
    })


def me(event):
    """GET /api/users/me - the account behind the token."""
    caller = auth.current_user(event)
    user = user_model.find_by_id(caller["id"])
    if user is None:
        raise HttpError(401, "Account no longer exists")
    return ok(user_view.serialize(user))


def list_users(event):
    """GET /api/users?role=engineer - all accounts. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    role = query_params(event).get("role")
    if role is not None and role not in auth.ALL_ROLES:
        raise HttpError(400, f"'role' must be one of: {', '.join(auth.ALL_ROLES)}")

    users = user_model.list_all(role)
    return ok(user_view.serialize_many(users))


def update_role(event, user_id):
    """PUT /api/users/{id}/role - promote or demote. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    body = json_body(event)
    role = validation.one_of(body, "role", auth.ALL_ROLES)

    if user_id == caller["id"]:
        raise HttpError(403, "You cannot change your own role")

    user = user_model.update_role(user_id, role)
    if user is None:
        raise HttpError(404, "User not found")

    logger.info("User %s role changed to %s by %s", user_id, role, caller["id"])
    return ok(user_view.serialize(user))


def delete_user(event, user_id):
    """DELETE /api/users/{id} - remove an account. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    if user_id == caller["id"]:
        raise HttpError(403, "You cannot delete your own account")

    try:
        deleted = user_model.delete(user_id)
    except user_model.UserInUse:
        raise HttpError(409, "User has incidents or messages and cannot be deleted")

    if deleted == 0:
        raise HttpError(404, "User not found")

    logger.info("User %s deleted by %s", user_id, caller["id"])
    return no_content()
