"""
Read-only view of the users table for the incidents service.

Assignment has to confirm the target account exists and holds a role allowed to
take tickets. Account management itself lives in the users service.
"""

from lib.database import fetch_one

def find_by_id(user_id):
    """Return id, name, email and role for one user, or None."""
    return fetch_one(
        "SELECT id, name, email, role FROM users WHERE id = %s",
        (user_id,),
    )
