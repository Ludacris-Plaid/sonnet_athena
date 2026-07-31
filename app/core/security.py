"""
Invite-code generation only — password hashing and JWT issuance moved to
Supabase Auth (see app/core/supabase_auth.py for token verification).
"""
import secrets
import string


def generate_invite_code(length: int = 10) -> str:
    """Generate a human-friendly invite code, e.g. RLTY-7K2QX9AB"""
    alphabet = string.ascii_uppercase + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"RLTY-{body}"
