"""
Repositories for Users, Credentials, OTP LoginCodes, and Chat History.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from config import settings
from core.security import (
    decrypt_api_key,
    encrypt_api_key,
    generate_otp_code,
    hash_otp_code,
    normalize_phone,
)
from db.models import ApiCredential, ChatMessageRecord, LoginCode, User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── User / Allowlist Management ──────────────────────────────────────────────

def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.get(User, user_id)


def get_user_by_phone(db: Session, raw_phone: str) -> Optional[User]:
    try:
        phone_e164 = normalize_phone(raw_phone)
    except ValueError:
        return None
    stmt = select(User).where(User.phone_e164 == phone_e164)
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_telegram_id(db: Session, telegram_user_id: int) -> Optional[User]:
    stmt = select(User).where(User.telegram_user_id == telegram_user_id)
    return db.execute(stmt).scalar_one_or_none()


def list_all_users(db: Session) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def upsert_allowed_user(
    db: Session,
    raw_phone: str,
    role: str = "user",
    display_name: Optional[str] = None,
    is_active: bool = True,
) -> User:
    """Adds a phone number to the allowlist or updates its role/active state."""
    phone_e164 = normalize_phone(raw_phone)
    user = get_user_by_phone(db, phone_e164)
    if user:
        user.role = role
        user.is_active = is_active
        if display_name:
            user.display_name = display_name
    else:
        user = User(
            phone_e164=phone_e164,
            role=role,
            display_name=display_name,
            is_active=is_active,
        )
        db.add(user)
    db.flush()
    return user


def remove_allowed_user(db: Session, raw_phone: str) -> bool:
    user = get_user_by_phone(db, raw_phone)
    if not user:
        return False
    db.delete(user)
    db.flush()
    return True


def link_telegram_account(
    db: Session,
    user: User,
    telegram_user_id: int,
    telegram_username: Optional[str] = None,
    display_name: Optional[str] = None,
) -> User:
    user.telegram_user_id = telegram_user_id
    if telegram_username:
        user.telegram_username = telegram_username
    if display_name and not user.display_name:
        user.display_name = display_name
    user.last_login_at = utcnow()
    db.flush()
    return user


def seed_admin_phones(db: Session) -> int:
    """Seeds initial admin phone numbers from settings.admin_phone_list on startup."""
    count = 0
    for raw in settings.admin_phone_list:
        try:
            upsert_allowed_user(db, raw, role="admin", is_active=True)
            count += 1
        except ValueError as exc:
            print(f"[AuthSeed] Skipping invalid ADMIN_PHONES entry '{raw}': {exc}")
    return count


# ─── BYOK API Credential Management ───────────────────────────────────────────

def get_user_credential(db: Session, user_id: str, provider: str = "groq") -> Optional[ApiCredential]:
    stmt = select(ApiCredential).where(
        ApiCredential.user_id == user_id,
        ApiCredential.provider == provider,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_decrypted_groq_key(db: Session, user_id: str) -> Optional[str]:
    cred = get_user_credential(db, user_id, provider="groq")
    if not cred:
        return None
    return decrypt_api_key(cred.key_ciphertext)


def save_user_groq_key(db: Session, user_id: str, plain_key: str) -> ApiCredential:
    ciphertext, last4 = encrypt_api_key(plain_key)
    now = utcnow()
    cred = get_user_credential(db, user_id, provider="groq")
    if cred:
        cred.key_ciphertext = ciphertext
        cred.key_last4 = last4
        cred.validated_at = now
        cred.updated_at = now
    else:
        cred = ApiCredential(
            user_id=user_id,
            provider="groq",
            key_ciphertext=ciphertext,
            key_last4=last4,
            validated_at=now,
        )
        db.add(cred)
    db.flush()
    return cred


def delete_user_groq_key(db: Session, user_id: str) -> bool:
    cred = get_user_credential(db, user_id, provider="groq")
    if not cred:
        return False
    db.delete(cred)
    db.flush()
    return True


# ─── OTP Login Codes (sent via Telegram Bot) ──────────────────────────────────

def create_login_otp(db: Session, user_id: str) -> tuple[str, LoginCode]:
    """Creates a fresh 6-digit OTP code for user_id, invalidating previous unconsumed codes."""
    db.execute(
        delete(LoginCode).where(
            LoginCode.user_id == user_id,
            LoginCode.consumed_at.is_(None),
        )
    )
    code, code_hash = generate_otp_code()
    expires = utcnow() + timedelta(seconds=settings.otp_ttl_seconds)
    record = LoginCode(
        user_id=user_id,
        code_hash=code_hash,
        expires_at=expires,
        attempts=0,
    )
    db.add(record)
    db.flush()
    return code, record


def verify_login_otp(db: Session, user_id: str, submitted_code: str) -> tuple[bool, str]:
    stmt = (
        select(LoginCode)
        .where(LoginCode.user_id == user_id, LoginCode.consumed_at.is_(None))
        .order_by(LoginCode.created_at.desc())
    )
    record = db.execute(stmt).scalars().first()
    if not record:
        return False, "No active login code found. Please request a new code."

    now = utcnow()
    exp = record.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now > exp:
        return False, "Login code has expired. Please request a new one."

    if record.attempts >= settings.otp_max_attempts:
        return False, "Too many failed attempts. Please request a new code."

    record.attempts += 1
    expected_hash = hash_otp_code(submitted_code)
    if record.code_hash != expected_hash:
        db.flush()
        return False, "Invalid verification code."

    record.consumed_at = now
    db.flush()
    return True, "Verified."


# ─── Persistent Chat History ──────────────────────────────────────────────────

def append_chat_message(
    db: Session,
    user_id: str,
    role: str,
    content: str,
    media_id: Optional[str] = None,
    channel: str = "telegram",
) -> ChatMessageRecord:
    msg = ChatMessageRecord(
        user_id=user_id,
        media_id=media_id,
        channel=channel,
        role=role,
        content=content,
    )
    db.add(msg)
    db.flush()
    return msg


def get_recent_chat_messages(
    db: Session,
    user_id: str,
    media_id: Optional[str] = None,
    limit: int = 12,
) -> list[ChatMessageRecord]:
    stmt = select(ChatMessageRecord).where(ChatMessageRecord.user_id == user_id)
    if media_id is None:
        stmt = stmt.where(ChatMessageRecord.media_id.is_(None))
    else:
        stmt = stmt.where(ChatMessageRecord.media_id == media_id)
    stmt = stmt.order_by(ChatMessageRecord.created_at.desc()).limit(limit)
    rows = list(db.execute(stmt).scalars().all())
    rows.reverse()
    return rows


def clear_chat_history(db: Session, user_id: str, media_id: Optional[str] = None) -> int:
    stmt = delete(ChatMessageRecord).where(ChatMessageRecord.user_id == user_id)
    if media_id is None:
        stmt = stmt.where(ChatMessageRecord.media_id.is_(None))
    else:
        stmt = stmt.where(ChatMessageRecord.media_id == media_id)
    res = db.execute(stmt)
    db.flush()
    return res.rowcount or 0

