"""
Message view: turns joined message rows into JSON for the frontend.
"""

def serialize(row):
    """Render one message row."""
    return {
        "id": row["id"],
        "incidentId": row["incident_id"],
        "message": row["message"],
        "author": {
            "id": row["user_id"],
            "name": row["author_name"],
            "email": row["author_email"],
            "role": row["author_role"],
        },
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }

def serialize_many(rows):
    """Render a thread of message rows."""
    return [serialize(row) for row in rows]
