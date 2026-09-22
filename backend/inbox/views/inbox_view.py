"""
Inbox view: turns unread summaries into JSON for the frontend.
"""

def serialize_item(row):
    """Render one ticket with unread activity."""
    return {
        "incident": {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "priority": row["priority"],
        },
        "unreadCount": row["unread_count"],
        "latestMessage": {
            "message": row["latest_message"],
            "createdAt": row["latest_at"],
            "author": {
                "id": row["latest_author_id"],
                "name": row["latest_author_name"],
            },
        },
    }

def serialize_inbox(rows, total_unread):
    """Render the inbox list plus the overall count for the nav badge."""
    return {
        "unread": total_unread,
        "items": [serialize_item(row) for row in rows],
    }

def serialize_count(total_unread):
    """Render just the count, for cheap polling."""
    return {"unread": total_unread}

def serialize_read(row, total_unread):
    """Render the result of marking a ticket read."""
    return {
        "incidentId": row["incident_id"],
        "lastReadAt": row["last_read_at"],
        "unread": total_unread,
    }
