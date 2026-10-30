from typing import Optional
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import phonenumbers
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from config import settings


# ─── Phone Number Normalization (E.164) ───────────────────────────────────────

def normalize_phone(raw_phone: str, default_region: Optional[str] = None) -> str:
    """
    Normalize any phone input (e.g. '+55 11 99999-9999', '5511999999999', '11999999999')
    into strict E.164 format ('+5511999999999').
    Raises ValueError if invalid.
    """
    cleaned = raw_phone.strip()
    if not cleaned:
        raise ValueError("Phone number cannot be empty.")

    # Telegram contacts sometimes omit the leading '+'
    if cleaned.isdigit() and len(cleaned) >= 10 and not cleaned.startswith("+"):
        try_plus = "+" + cleaned
        try:
            parsed = phonenumbers.parse(try_plus, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            pass

    region = default_region or settings.default_phone_region or "BR"
    parsed = phonenumbers.parse(cleaned, region)
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Invalid phone number: {raw_phone}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


# ─── Fernet Encryption for BYOK API Keys ──────────────────────────────────────

_fernet_instance: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    key = (settings.app_encryption_key or "").strip()
    if not key:
        # Derive a deterministic 32-byte url-safe base64 Fernet key from jwt_secret or dev fallback
        # so local dev works out of the box, while production uses explicit APP_ENCRYPTION_KEY.
        import base64
        seed = (settings.jwt_secret or "whappend-local-dev-secret-change-in-prod").encode("utf-8")
        digest = hashlib.sha256(seed).digest()
        key = base64.urlsafe_b64encode(digest).decode("ascii")

    _fernet_instance = Fernet(key.encode("ascii"))
    return _fernet_instance


def encrypt_api_key(plain_key: str) -> tuple[str, str]:
    """Returns (ciphertext, last4)."""
    trimmed = plain_key.strip()
    token = _get_fernet().encrypt(trimmed.encode("utf-8")).decode("ascii")
    last4 = trimmed[-4:] if len(trimmed) >= 4 else trimmed
    return token, last4


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored API key could not be decrypted (APP_ENCRYPTION_KEY mismatch). Please set your key again.",
        ) from exc


def validate_groq_api_key(api_key: str) -> tuple[bool, Optional[str]]:
    """Checks against Groq's API that the provided key is valid and active."""
    cleaned = (api_key or "").strip()
    if not cleaned:
        return False, "API key is empty."
    try:
        from groq import Groq
        client = Groq(api_key=cleaned)
        client.models.list()
        return True, None
    except Exception as exc:
        msg = str(exc)
        # Never echo the full key back in error logs/messages
        if len(cleaned) > 8:
            msg = msg.replace(cleaned, "gsk_***REDACTED***")
        return False, msg


def mask_key_in_text(text: str) -> str:
    """Scrubs any accidental gsk_... tokens from logs or error messages."""
    import re
    return re.sub(r"gsk_[A-Za-z0-9]{10,}", "gsk_***REDACTED***", text or "")


# ─── JWT Session Tokens ───────────────────────────────────────────────────────

def _jwt_secret() -> str:
    return (settings.jwt_secret or "whappend-local-dev-jwt-secret-change-me").strip()


def create_access_token(user_id: str, phone_e164: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "phone": phone_e164,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.") from exc


# ─── OTP Code Hashing & Verification ──────────────────────────────────────────

def generate_otp_code() -> tuple[str, str]:
    """Returns (6-digit code, sha256 hex digest)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    return code, hash_otp_code(code)


def hash_otp_code(code: str) -> str:
    secret = _jwt_secret().encode("utf-8")
    return hmac.new(secret, code.strip().encode("utf-8"), hashlib.sha256).hexdigest()


# ─── Telegram Login Widget HMAC Verification ──────────────────────────────────

def verify_telegram_login_widget(data: dict, max_age_seconds: int = 86400) -> dict:
    """
    Verifies payload from the official Telegram Login Widget:
    https://core.telegram.org/widgets/login#checking-authorization
    """
    bot_token = (settings.telegram_bot_token or "").strip()
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TELEGRAM_BOT_TOKEN is not configured on the backend.",
        )

    payload = dict(data)
    received_hash = payload.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Telegram signature hash.")

    auth_date = int(payload.get("auth_date", 0))
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if now_ts - auth_date > max_age_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram login data has expired.")

    check_lines = [f"{k}={v}" for k, v in sorted(payload.items()) if v is not None]
    data_check_string = "\n".join(check_lines)

    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, str(received_hash)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram login signature.")

    return payload

