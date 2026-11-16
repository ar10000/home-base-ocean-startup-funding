"""Record IDs (handbook section 11: every table's `id` is a UUIDv7).

UUIDv7 starts with a millisecond timestamp, so IDs sort by creation time and keep
B-tree indexes compact. Python's standard library only gains uuid7 in 3.14.
"""

import uuid

import uuid6


def new_id() -> uuid.UUID:
    """A new UUIDv7, as a standard `uuid.UUID`."""
    return uuid.UUID(bytes=uuid6.uuid7().bytes)
