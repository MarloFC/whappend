"""
Admin router for managing the phone number allowlist (`/admin/users`).
Only accessible to users with `role == "admin"`.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.deps import get_current_admin
from core.repositories import (
    get_user_credential,
    list_all_users,
    remove_allowed_user,
    upsert_allowed_user,
)
from core.security import normalize_phone
from db.base import get_db
from db.models import User

router = APIRouter(prefix="/admin/users", tags=["admin"])


class AllowedUserInput(BaseModel):
    phone: str
    role: str = "user"  # "user" | "admin"
    display_name: Optional[str] = None
    is_active: bool = True


class AllowedUserItem(BaseModel):
    id: str
    phone_e164: str
    role: str
    is_active: bool
    display_name: Optional[str] = None
    telegram_user_id: Optional[int] = None
    telegram_username: Optional[str] = None
    has_groq_key: bool = False
    groq_key_last4: Optional[str] = None
    created_at: datetime


def _to_item(db: Session, u: User) -> AllowedUserItem:
    cred = get_user_credential(db, u.id, provider="groq")
    return AllowedUserItem(
        id=u.id,
        phone_e164=u.phone_e164,
        role=u.role,
        is_active=u.is_active,
        display_name=u.display_name,
        telegram_user_id=u.telegram_user_id,
        telegram_username=u.telegram_username,
        has_groq_key=cred is not None,
        groq_key_last4=cred.key_last4 if cred else None,
        created_at=u.created_at,
    )


@router.get("", response_model=list[AllowedUserItem])
async def list_allowed_users(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    users = list_all_users(db)
    return [_to_item(db, u) for u in users]


@router.post("", response_model=AllowedUserItem)
async def add_or_update_allowed_user(
    body: AllowedUserInput,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    role = body.role if body.role in ("user", "admin") else "user"
    try:
        user = upsert_allowed_user(
            db,
            raw_phone=body.phone,
            role=role,
            display_name=body.display_name,
            is_active=body.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_item(db, user)


@router.delete("/{phone}")
async def delete_allowed_user(
    phone: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        norm = normalize_phone(phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if norm == admin.phone_e164:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin phone number.",
        )

    removed = remove_allowed_user(db, norm)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found in allowlist.")
    return {"removed": True, "phone_e164": norm}

