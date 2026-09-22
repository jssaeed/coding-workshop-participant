# Copied from backend/_shared/validation.py by bin/sync-shared.sh - do not edit.
"""
Checking request input, shared by every service.

Each function looks at one field of the request body. It returns the cleaned
value, or raises HttpError(400) with a message that names the field, so the
frontend can show it next to the right input.
"""

import re

from .responses import HttpError

# Good enough to catch typos like "bob@" or "bob.example.com".
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8
# bcrypt ignores everything after 72 bytes, so refuse longer passwords rather
# than silently using only part of them.
MAX_PASSWORD_BYTES = 72


def required_string(body, field, max_length=None):
    """The field must be present and not blank. Returns it trimmed."""
    value = body.get(field)
    if not isinstance(value, str) or value.strip() == "":
        raise HttpError(400, f"'{field}' is required")

    value = value.strip()
    if max_length is not None and len(value) > max_length:
        raise HttpError(400, f"'{field}' must be {max_length} characters or fewer")
    return value


def optional_string(body, field, max_length=None):
    """Like required_string, but a missing field gives ''."""
    value = body.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise HttpError(400, f"'{field}' must be text")

    value = value.strip()
    if max_length is not None and len(value) > max_length:
        raise HttpError(400, f"'{field}' must be {max_length} characters or fewer")
    return value


def email(body):
    """A valid-looking email address, in lower case."""
    value = required_string(body, "email", max_length=255).lower()
    if not EMAIL_PATTERN.match(value):
        raise HttpError(400, "'email' must be a valid email address")
    return value


def password(body):
    """A password of acceptable length."""
    value = body.get("password")
    if not isinstance(value, str) or value == "":
        raise HttpError(400, "'password' is required")
    if len(value) < MIN_PASSWORD_LENGTH:
        raise HttpError(400, f"'password' must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HttpError(400, f"'password' must be {MAX_PASSWORD_BYTES} bytes or fewer")
    return value


def one_of(body, field, allowed, default=None):
    """The field must be one of the allowed values."""
    value = body.get(field)
    if value is None:
        if default is not None:
            return default
        raise HttpError(400, f"'{field}' is required")
    if value not in allowed:
        raise HttpError(400, f"'{field}' must be one of: {', '.join(allowed)}")
    return value


def integer_in_range(body, field, minimum, maximum, default=None):
    """The field must be a whole number between minimum and maximum."""
    value = body.get(field)
    if value is None:
        if default is not None:
            return default
        raise HttpError(400, f"'{field}' is required")

    # In Python, True and False count as numbers (1 and 0). Reject them.
    if isinstance(value, bool) or not isinstance(value, int):
        raise HttpError(400, f"'{field}' must be a whole number")
    if value < minimum or value > maximum:
        raise HttpError(400, f"'{field}' must be between {minimum} and {maximum}")
    return value


def optional_id(body, field):
    """A record id (positive whole number), or None when the field is absent."""
    value = body.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise HttpError(400, f"'{field}' must be a positive whole number")
    return value


def required_id(body, field):
    """A record id that must be present."""
    value = optional_id(body, field)
    if value is None:
        raise HttpError(400, f"'{field}' is required")
    return value
