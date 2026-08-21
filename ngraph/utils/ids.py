from __future__ import annotations

import base64
import uuid


def new_base64_uuid() -> str:
    """Return a 22-character URL-safe Base64-encoded UUID without padding.

    The 16 raw bytes of a random version 4 UUID are encoded with URL-safe
    Base64; the two trailing padding characters are dropped, leaving 22 ASCII
    characters.

    Returns:
        A 22-character URL-safe Base64 representation of a UUID4, unpadded.
    """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode("ascii")
