"""
Building view: turns a buildings row into the JSON the frontend expects.
"""


def serialize(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "floors": row["floors"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def serialize_many(rows):
    return [serialize(row) for row in rows]
