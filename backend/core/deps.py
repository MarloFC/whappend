"""
FastAPI Dependencies for Auth, User resolution, and BYOK Groq Key resolution.
"""

from typing import Optional
from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.repositories import get_decrypted_groq_key, get_user_by_id
from core.security import decode_access_token
from db.base import get_db
from db.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    token_query: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticates the request via `Authorization: Bearer <jwt>` (or `?token=<jwt>` for `<video src>` streaming)
    and verifies the user is still active in the allowlist.
    """
    raw_token = (credentials.credentials if credentials else None) or token_query
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in with an allowed phone number.",
        )

    payload = decode_access_token(raw_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    user = get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not on the active allowlist.",
        )
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return user


def resolve_user_groq_key(
    user: User = Depends(get_current_user),
    x_groq_api_key: Optional[str] = Header(None, alias="X-Groq-Api-Key"),
    db: Session = Depends(get_db),
) -> str:
    """
    Resolves the authenticated user's Groq API key.
    Priority:
      1. Encrypted BYOK key stored in the database for this user
      2. Explicit X-Groq-Api-Key header (if sent by client)
    Never falls back to any server-wide key.
    """
    stored_key = get_decrypted_groq_key(db, user.id)
    if stored_key:
        return stored_key

    header_key = (x_groq_api_key or "").strip()
    if header_key:
        return header_key

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No Groq API key configured for your account. Please set your BYOK Groq API key in Settings or via /setkey on Telegram.",
    )

