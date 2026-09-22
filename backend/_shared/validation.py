"""
Input validation shared by every service.

Each helper either returns a clean value or raises HttpError(400) naming the
field that failed, so the frontend can show the message next to the input.
"""

import re

from .responses import HttpError

# Deliberately permissive: catches obvious typos without rejecting valid but
# unusual addresses.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# bcrypt only considers the first 72 bytes, so anything longer is silently
# truncated. Reject it instead of quietly ignoring part of the password.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8

def required_string(body, field, max_length=None):
    """Return a non-empty trimmed string, or raise 400."""
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HttpError(400, f"'{field}' is required")

    value = value.strip()
    if max_length and len(value) > max_length:
        raise HttpError(400, f"'{field}' must be {max_length} characters or fewer")
    return value

def optional_string(body, field, default="", max_length=None):
    """Return a trimmed string, falling back to a default when absent."""
    value = body.get(field)
    if value is None:
        return default
    if not isinstance(value, str):
        raise HttpError(400, f"'{field}' must be a string")

    value = value.strip()
    if max_length and len(value) > max_length:
        raise HttpError(400, f"'{field}' must be {max_length} characters or fewer")
    return value

def email(body, field="email"):
    """Return a lower-cased, syntactically valid email address."""
    value = required_string(body, field, max_length=255).lower()
    if not EMAIL_PATTERN.match(value):
        raise HttpError(400, "'email' must be a valid email address")
    return value

def password(body, field="password"):
    """Return a password that meets the length rules."""
    value = body.get(field)
    if not isinstance(value, str) or not value:
        raise HttpError(400, "'password' is required")
    if len(value) < MIN_PASSWORD_LENGTH:
        raise HttpError(400, f"'password' must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HttpError(400, f"'password' must be {MAX_PASSWORD_BYTES} bytes or fewer")
    return value

def one_of(body, field, allowed, default=None):
    """Return a value restricted to a fixed set."""
    value = body.get(field)
    if value is None:
        if default is not None:
            return default
        raise HttpError(400, f"'{field}' is required")
    if value not in allowed:
        raise HttpError(400, f"'{field}' must be one of: {', '.join(sorted(allowed))}")
    return value

def integer_in_range(body, field, minimum, maximum, default=None):
    """Return an int within an inclusive range."""
    value = body.get(field)
    if value is None:
        if default is not None:
            return default
        raise HttpError(400, f"'{field}' is required")

    # Reject booleans explicitly: in Python they are ints, so True would pass
    # as 1 without this check.
    if isinstance(value, bool) or not isinstance(value, int):
        raise HttpError(400, f"'{field}' must be an integer")
    if not minimum <= value <= maximum:
        raise HttpError(400, f"'{field}' must be between {minimum} and {maximum}")
    return value

def positive_id(body, field, required=True):
    """Return a positive integer id, allowing null when not required."""
    value = body.get(field)
    if value is None:
        if required:
            raise HttpError(400, f"'{field}' is required")
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise HttpError(400, f"'{field}' must be a positive integer")
    return value
