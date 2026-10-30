"""
Authentication router:
1. Phone + OTP delivered via Telegram bot (`/auth/otp/request`, `/auth/otp/verify`)
2. Official Telegram Login Widget (`/auth/telegram-widget`)
3. Current session user (`/auth/me`)
4. Standalone key validator (`/auth/validate-key`)
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from core.deps import get_current_user
from core.repositories import (
    create_login_otp,
    get_user_by_phone,
    get_user_by_telegram_id,
    get_user_credential,
    link_telegram_account,
    verify_login_otp,
)
from core.security import (
    create_access_token,
    normalize_phone,
    validate_groq_api_key,
    verify_telegram_login_widget,
)
from db.base import get_db
from db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class UserProfileResponse(BaseModel):
    id: str
    phone_e164: str
    telegram_user_id: Optional[int] = None
    telegram_username: Optional[str] = None
    display_name: Optional[str] = None
    role: str
    has_groq_key: bool
    groq_key_last4: Optional[str] = None
    groq_key_validated_at: Optional[datetime] = None


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileResponse


class OtpRequestBody(BaseModel):
    phone: str


class OtpRequestResponse(BaseModel):
    sent: bool
    phone_e164: str
    delivery: str  # "telegram" | "dev_console"
    message: str
    dev_code: Optional[str] = None


class OtpVerifyBody(BaseModel):
    phone: str
    code: str


class TelegramWidgetPayload(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class KeyValidateRequest(BaseModel):
    api_key: Optional[str] = None


def _build_user_profile(db: Session, user: User) -> UserProfileResponse:
    cred = get_user_credential(db, user.id, provider="groq")
    return UserProfileResponse(
        id=user.id,
        phone_e164=user.phone_e164,
        telegram_user_id=user.telegram_user_id,
        telegram_username=user.telegram_username,
        display_name=user.display_name,
        role=user.role,
        has_groq_key=cred is not None,
        groq_key_last4=cred.key_last4 if cred else None,
        groq_key_validated_at=cred.validated_at if cred else None,
    )


# ─── 1. Phone + OTP via Telegram Bot ──────────────────────────────────────────

@router.post("/otp/request", response_model=OtpRequestResponse)
async def request_otp(body: OtpRequestBody, db: Session = Depends(get_db)):
    """
    Step 1 of Phone + Code login:
    Checks that the phone number is on the allowlist, generates a 6-digit OTP,
    and sends it to the user via the Telegram bot.
    """
    try:
        phone_e164 = normalize_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = get_user_by_phone(db, phone_e164)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This phone number is not on the allowlist. Ask the administrator to authorize it.",
        )

    code, _ = create_login_otp(db, user.id)

    # Deliver via Telegram bot if user has linked their Telegram account & bot token is configured
    if user.telegram_user_id and settings.telegram_bot_token:
        from bot.app import send_telegram_text
        sent_ok = await send_telegram_text(
            chat_id=user.telegram_user_id,
            text=(
                f"🔐 <b>WhAppend Web Login Code</b>\n\n"
                f"Your one-time verification code is: <code>{code}</code>\n"
                f"Expires in {settings.otp_ttl_seconds // 60} minutes.\n\n"
                f"<i>If you did not request this code, ignore this message.</i>"
            ),
        )
        if sent_ok:
            return OtpRequestResponse(
                sent=True,
                phone_e164=phone_e164,
                delivery="telegram",
                message="Verification code sent to your Telegram chat with the bot!",
            )

    # If user hasn't linked their Telegram account yet:
    if settings.telegram_bot_token and not user.telegram_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Your phone number is allowed, but you haven't linked your Telegram account yet. "
                "Open the WhAppend Telegram bot first, send /start, and tap 'Share my phone number' — "
                "then request the web login code again."
            ),
        )

    # Local dev fallback when TELEGRAM_BOT_TOKEN is not set yet: print code to server console
    print(f"\n[DEV OTP] Login code for {phone_e164}: {code}\n")
    return OtpRequestResponse(
        sent=True,
        phone_e164=phone_e164,
        delivery="dev_console",
        message="TELEGRAM_BOT_TOKEN not configured — dev code generated (check server console or response).",
        dev_code=code,
    )


@router.post("/otp/verify", response_model=AuthTokenResponse)
async def verify_otp(body: OtpVerifyBody, db: Session = Depends(get_db)):
    """Step 2 of Phone + Code login: verifies the 6-digit code and returns a JWT."""
    try:
        phone_e164 = normalize_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = get_user_by_phone(db, phone_e164)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Phone number is not allowed.")

    ok, reason = verify_login_otp(db, user.id, body.code)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=reason)

    token = create_access_token(user_id=user.id, phone_e164=user.phone_e164, role=user.role)
    return AuthTokenResponse(
        access_token=token,
        user=_build_user_profile(db, user),
    )


# ─── 2. Official Telegram Login Widget ────────────────────────────────────────

@router.post("/telegram-widget", response_model=AuthTokenResponse)
async def login_telegram_widget(payload: TelegramWidgetPayload, db: Session = Depends(get_db)):
    """
    Verifies the HMAC-SHA256 signature from the Telegram Login Widget and signs in
    the user if their `telegram_user_id` is linked to an allowlisted phone number.
    """
    verified = verify_telegram_login_widget(payload.model_dump(exclude_none=True))
    tg_id = int(verified["id"])

    user = get_user_by_telegram_id(db, tg_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This Telegram account is not linked to an allowed phone number yet. "
                "Open the WhAppend Telegram bot, send /start, and share your phone number first."
            ),
        )

    full_name = " ".join(filter(None, [payload.first_name, payload.last_name])) or None
    link_telegram_account(
        db,
        user=user,
        telegram_user_id=tg_id,
        telegram_username=payload.username,
        display_name=full_name,
    )

    token = create_access_token(user_id=user.id, phone_e164=user.phone_e164, role=user.role)
    return AuthTokenResponse(
        access_token=token,
        user=_build_user_profile(db, user),
    )


# ─── 3. Current User Profile ──────────────────────────────────────────────────

@router.get("/me", response_model=UserProfileResponse)
async def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _build_user_profile(db, user)


# ─── 4. Standalone Key Validation ─────────────────────────────────────────────

@router.post("/validate-key")
async def validate_key(
    body: Optional[KeyValidateRequest] = None,
    x_groq_api_key: Optional[str] = Header(None, alias="X-Groq-Api-Key"),
):
    """Validates if a provided Groq API key is active and authorized."""
    key = (x_groq_api_key or (body.api_key if body else "") or "").strip()
    if not key:
        return {"valid": False, "error": "No API key provided."}

    valid, err = validate_groq_api_key(key)
    if valid:
        return {"valid": True, "message": "Groq API key is valid and connected!"}
    return {"valid": False, "error": err or "Invalid Groq API key."}

