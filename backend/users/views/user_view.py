"""
User view: turns database rows into the JSON shape the frontend consumes.

Keys are camelCase to match JavaScript conventions, and timestamps are left as
datetimes for the response encoder to render as ISO-8601.
"""

def serialize(row):
    """Render one user row."""
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }

def serialize_many(rows):
    """Render a list of user rows."""
    return [serialize(row) for row in rows]

def with_token(row, token):
    """Render the login response: the user plus their access token."""
    return {"user": serialize(row), "token": token}
