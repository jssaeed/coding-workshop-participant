"""
User controller: the rules for accounts.

- Anyone with a company email (ending in @acme.inc) can create an account;
  it is always an employee.
- Anyone can log in. Login returns a short-lived access token and a
  long-lived refresh token; /refresh swaps a refresh token for new ones.
- Only an admin can list users, change roles, or delete accounts. Demoting
  someone also revokes their refresh tokens, so their session cannot
  continue past the current access token.
- An admin cannot change or delete their own account (so the system can
  never end up with no admin).
"""

import logging

from lib import auth, validation
from lib.database import transaction
from lib.request import json_body, query_params
from lib.responses import HttpError, created, no_content, ok
from models import branch as branch_model
from models import refresh_token as refresh_token_model
from models import user as user_model
from views import branch_view, user_view

logger = logging.getLogger()

# Only company addresses may sign up. Compared after lower-casing, so
# Ana@ACME.INC is accepted.
COMPANY_EMAIL_DOMAIN = "@acme.inc"


def list_branches(event):
    """GET /api/users/branches - the sites a new account can pick from. Public."""
    return ok(branch_view.serialize_many(branch_model.list_all()))


def create_account(event):
    """POST /api/users - sign up. Always creates an employee, at the chosen branch."""
    body = json_body(event)
    email = validation.email(body)
    password = validation.password(body)
    name = validation.required_string(body, "name", max_length=255)
    branch_id = validation.required_id(body, "branchId")
    if branch_model.find_by_id(branch_id) is None:
        raise HttpError(400, "'branchId' does not match a known branch")

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
        branch_id=branch_id,
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

    with transaction():
        # Housekeeping: each login clears out refresh tokens that are expired
        # or revoked. Cheap, so the table never needs a separate cleanup job.
        refresh_token_model.delete_stale()
        result = issue_tokens(user)

    return ok(result)


def issue_tokens(user):
    """
    Build the login/refresh response: the user, a new access token and a
    new refresh token. The refresh token's hash is saved so it can be
    checked and revoked later.
    """
    user = user_model.find_by_id(user["id"])  # the full row, with the branch
    refresh_token, token_hash, expires_at = auth.create_refresh_token()
    refresh_token_model.create(user["id"], token_hash, expires_at)
    return {
        "user": user_view.serialize(user),
        "token": auth.create_access_token(user),
        "refreshToken": refresh_token,
    }


def refresh(event):
    """
    POST /api/users/refresh - swap a refresh token for a new pair of tokens.

    The old refresh token is revoked as part of this ("rotation"), so each
    one can be used exactly once. The new access token carries the user's
    CURRENT role, read from the database.
    """
    body = json_body(event)
    refresh_token = body.get("refreshToken")
    if not isinstance(refresh_token, str) or refresh_token == "":
        raise HttpError(400, "'refreshToken' is required")

    row = refresh_token_model.find_valid(auth.hash_refresh_token(refresh_token))
    if row is None:
        raise HttpError(401, "Refresh token is invalid or expired")

    # Revoke and re-issue together: a failure half-way must not leave the
    # user with no refresh token at all, or with two valid ones.
    with transaction():
        refresh_token_model.revoke(row["token_id"])
        result = issue_tokens(row)

    return ok(result)


def logout(event):
    """POST /api/users/logout - revoke the given refresh token."""
    body = json_body(event)
    refresh_token = body.get("refreshToken")
    if isinstance(refresh_token, str) and refresh_token:
        refresh_token_model.revoke_by_hash(auth.hash_refresh_token(refresh_token))
    return no_content()


def me(event):
    """GET /api/users/me - the account behind the token."""
    caller = auth.current_user(event)
    user = user_model.find_by_id(caller["id"])
    if user is None:
        raise HttpError(401, "Account no longer exists")
    return ok(user_view.serialize(user))


def get_user_i_may_manage(caller, user_id):
    """
    Load a user the caller wants to manage, or raise.

    404 if there is no such user. A db admin may manage anyone. A facility
    admin only manages the people at their own branch (403 otherwise), and
    never a db admin (403).
    """
    user = user_model.find_by_id(user_id)
    if user is None:
        raise HttpError(404, "User not found")
    if auth.is_db_admin(caller):
        return user
    if user["branch_id"] != caller["branch_id"]:
        raise HttpError(403, "That user belongs to another branch")
    if user["role"] == auth.ROLE_DB_ADMIN:
        raise HttpError(403, "Only a db admin can manage a db admin account")
    return user


def list_users(event):
    """
    GET /api/users?role=engineer - the accounts the caller may manage.

    A facility admin sees their own branch; a db admin sees every branch.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN, auth.ROLE_DB_ADMIN])

    role = query_params(event).get("role")
    if role is not None and role not in auth.ALL_ROLES:
        raise HttpError(400, f"'role' must be one of: {', '.join(auth.ALL_ROLES)}")

    branch_id = None if auth.is_db_admin(caller) else caller["branch_id"]
    users = user_model.list_all(branch_id, role)
    return ok(user_view.serialize_many(users))


def update_role(event, user_id):
    """
    PUT /api/users/{id}/role - promote or demote.

    A db admin can give anyone any role. A facility admin can give people
    at their branch any role except db admin.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN, auth.ROLE_DB_ADMIN])

    body = json_body(event)
    allowed_roles = auth.ALL_ROLES if auth.is_db_admin(caller) else auth.BRANCH_ROLES
    role = validation.one_of(body, "role", allowed_roles)

    if user_id == caller["id"]:
        raise HttpError(403, "You cannot change your own role")

    before = get_user_i_may_manage(caller, user_id)

    # Taking power away must also end the user's sessions: their current
    # access token dies within minutes and cannot be renewed. A promotion
    # keeps their sessions; the new role applies on their next request.
    # The role change and the revoke are one transaction, so a demoted user
    # can never be left with a working refresh token.
    with transaction():
        user = user_model.update_role(user_id, role)
        if auth.is_demotion(before["role"], role):
            refresh_token_model.revoke_all_for_user(user_id)

    logger.info("User %s role changed to %s by %s", user_id, role, caller["id"])
    return ok(user_view.serialize(user))


def delete_user(event, user_id):
    """DELETE /api/users/{id} - remove an account. Facility admin (own branch) or db admin."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN, auth.ROLE_DB_ADMIN])

    if user_id == caller["id"]:
        raise HttpError(403, "You cannot delete your own account")

    get_user_i_may_manage(caller, user_id)

    # Their tickets and messages are kept and shown as "Deleted user".
    user_model.delete(user_id)

    logger.info("User %s deleted by %s", user_id, caller["id"])
    return no_content()
