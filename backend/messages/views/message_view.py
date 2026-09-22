"""
Message view: turns a joined message row into the JSON the frontend expects.
"""


def serialize(row):
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
    return [serialize(row) for row in rows]
