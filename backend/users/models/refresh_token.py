"""
Refresh-token model: the SQL for the refresh_tokens table.

A refresh token is valid when its hash is in this table, it has not expired,
and revoked_at is still NULL.
"""

from lib.database import execute, fetch_one


def create(user_id, token_hash, expires_at):
    """Store a new refresh token (its hash) for a user."""
    execute(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES (%s, %s, %s)
        """,
        (user_id, token_hash, expires_at),
    )


def find_valid(token_hash):
    """
    Return the token row joined with its user if the token is still usable,
    otherwise None.
    """
    return fetch_one(
        """
        SELECT t.id AS token_id,
               u.id, u.email, u.name, u.role, u.created_at, u.updated_at
        FROM refresh_tokens t
        JOIN users u ON u.id = t.user_id
        WHERE t.token_hash = %s
          AND t.revoked_at IS NULL
          AND t.expires_at > NOW()
        """,
        (token_hash,),
    )


def revoke(token_id):
    """Mark one token as no longer usable."""
    execute(
        "UPDATE refresh_tokens SET revoked_at = NOW() WHERE id = %s AND revoked_at IS NULL",
        (token_id,),
    )


def revoke_by_hash(token_hash):
    """Mark one token as no longer usable, found by its hash (logout)."""
    execute(
        "UPDATE refresh_tokens SET revoked_at = NOW() WHERE token_hash = %s AND revoked_at IS NULL",
        (token_hash,),
    )


def revoke_all_for_user(user_id):
    """Sign the user out everywhere (used when they are demoted)."""
    execute(
        "UPDATE refresh_tokens SET revoked_at = NOW() WHERE user_id = %s AND revoked_at IS NULL",
        (user_id,),
    )


def delete_stale():
    """
    Remove tokens that can never be used again: expired ones, and ones that
    were revoked (used, logged out, or demoted). Called on every login so the
    table cannot grow without bound. Returns how many rows were removed.
    """
    return execute(
        "DELETE FROM refresh_tokens WHERE expires_at < NOW() OR revoked_at IS NOT NULL"
    )
