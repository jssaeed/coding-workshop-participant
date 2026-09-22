"""
A read-only look at the users table, for checking who a ticket is assigned to.

Creating and editing users happens in the users service, not here.
"""

from lib.database import fetch_one


def find_by_id(user_id):
    return fetch_one(
        "SELECT id, name, email, role FROM users WHERE id = %s",
        (user_id,),
    )
