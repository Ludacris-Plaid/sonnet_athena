"""
Shared FastAPI dependencies: current user extraction from a Supabase JWT.
"""
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.supabase_auth import verify_supabase_token
from app.models.org import User


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        claims = verify_supabase_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    supabase_user_id = claims.get("sub")
    if not supabase_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject claim")

    user = db.query(User).filter(User.id == supabase_user_id).first()
    if not user:
        # Valid Supabase session, but no RealtyAI profile/org yet — this is
        # the state right after Supabase signup, before an invite code has
        # been redeemed. Distinct status so the frontend can route to the
        # "finish setting up your account" step instead of a generic error.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No RealtyAI profile found for this account yet — complete signup with an invite code first.",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
