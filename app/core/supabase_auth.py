"""
Verifies Supabase-issued JWTs via the Supabase GoTrue user API (primary),
with HS256 shared-secret and JWKS fallbacks.
"""
from functools import lru_cache
import httpx
import jwt as pyjwt
from jwt import PyJWKClient
from app.core.config import settings


def verify_supabase_token(token: str) -> dict:
    # 1) Dev-mode token (HS256 signed with SECRET_KEY)
    try:
        dev_claims = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_aud": False})
        if dev_claims.get("dev_mode"):
            return dev_claims
    except pyjwt.PyJWTError:
        pass

    # 2) Legacy HS256 shared secret
    if settings.SUPABASE_JWT_SECRET:
        try:
            return pyjwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        except pyjwt.PyJWTError:
            pass

    # 3) JWKS (ES256/RS256)
    try:
        jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        return pyjwt.decode(token, signing_key.key, algorithms=["ES256", "RS256"], audience="authenticated")
    except Exception:
        pass

    # 4) Verify via Supabase GoTrue user API (works with any algorithm)
    try:
        resp = httpx.get(
            f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {token}",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "sub": data["id"],
                "email": data.get("email", ""),
                "role": data.get("role", "authenticated"),
            }
    except Exception:
        pass

    raise pyjwt.PyJWTError("Invalid token")
