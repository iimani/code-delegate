import uuid


def new_id(prefix: str) -> str:
    """Random identifier such as ``cus_1a2b3c4d5e6f``."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
