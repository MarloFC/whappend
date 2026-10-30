"""
BYOK Groq API Key management router (`/me/groq-key`).
Validates the user's Groq key, encrypts it with Fernet, and stores it in the DB.
Never returns the plaintext key — only `****last4` and validation timestamp.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.deps import get_current_user
from core.repositories import (
    delete_user_groq_key,
    get_user_credential,
    save_user_groq_key,
)
from core.security import validate_groq_api_key
from db.base import get_db
from db.models import User

router = APIRouter(prefix="/me/groq-key", tags=["keys"])


class SetGroqKeyRequest(BaseModel):
    api_key: str


class GroqKeyStatusResponse(BaseModel):
    configured: bool
    provider: str = "groq"
    masked_key: Optional[str] = None
    key_last4: Optional[str] = None
    validated_at: Optional[datetime] = None
    message: Optional[str] = None


@router.get("", response_model=GroqKeyStatusResponse)
async def get_my_groq_key_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cred = get_user_credential(db, user.id, provider="groq")
    if not cred:
        return GroqKeyStatusResponse(configured=False)
    return GroqKeyStatusResponse(
        configured=True,
        masked_key=f"gsk_••••{cred.key_last4}",
        key_last4=cred.key_last4,
        validated_at=cred.validated_at,
    )


@router.put("", response_model=GroqKeyStatusResponse)
async def set_my_groq_key(
    body: SetGroqKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cleaned = (body.api_key or "").strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key cannot be empty.")

    valid, error = validate_groq_api_key(cleaned)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Groq rejected this API key: {error}",
        )

    cred = save_user_groq_key(db, user.id, cleaned)
    return GroqKeyStatusResponse(
        configured=True,
        masked_key=f"gsk_••••{cred.key_last4}",
        key_last4=cred.key_last4,
        validated_at=cred.validated_at,
        message="Your Groq API key was verified, encrypted, and saved to your account!",
    )


@router.delete("", response_model=GroqKeyStatusResponse)
async def remove_my_groq_key(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_user_groq_key(db, user.id)
    return GroqKeyStatusResponse(
        configured=False,
        message="Your Groq API key was removed from the database.",
    )

