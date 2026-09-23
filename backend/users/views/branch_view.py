"""
Branch view: a branch row as JSON.
"""


def serialize(row):
    return {"id": row["id"], "name": row["name"]}


def serialize_many(rows):
    return [serialize(row) for row in rows]
