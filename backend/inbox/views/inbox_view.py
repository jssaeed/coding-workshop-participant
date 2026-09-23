"""
Inbox view: turns the grouped unread data into the JSON the frontend expects.
"""


def serialize_item(entry):
    latest = entry["latest_message"]

    # A null author means that account has since been deleted.
    if latest["author_id"] is None:
        author = None
    else:
        author = {"id": latest["author_id"], "name": latest["author_name"]}

    return {
        "incident": entry["incident"],
        "unreadCount": entry["unread_count"],
        "latestMessage": {
            "message": latest["message"],
            "createdAt": latest["created_at"],
            "author": author,
        },
    }


def serialize_inbox(entries):
    total = sum(entry["unread_count"] for entry in entries)
    return {
        "unread": total,
        "items": [serialize_item(entry) for entry in entries],
    }
