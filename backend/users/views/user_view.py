"""
User view: turns a database row into the JSON the frontend expects.

Keys are camelCase because that is the JavaScript convention.
"""


def serialize(row):
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def serialize_many(rows):
    return [serialize(row) for row in rows]
