"""
WhAppend CLI — Manage the phone number allowlist, users, and encryption keys.

Examples:
  python cli.py add-user +5511999999999 --admin --name "Marlon"
  python cli.py add-user +5511988887777
  python cli.py remove-user +5511988887777
  python cli.py list-users
  python cli.py generate-secrets
"""

import argparse
import secrets
import sys
from cryptography.fernet import Fernet

from core.repositories import (
    get_user_credential,
    list_all_users,
    remove_allowed_user,
    upsert_allowed_user,
)
from db.base import init_db, session_scope


def cmd_add_user(args: argparse.Namespace) -> None:
    init_db()
    role = "admin" if args.admin else "user"
    with session_scope() as db:
        user = upsert_allowed_user(
            db,
            raw_phone=args.phone,
            role=role,
            display_name=args.name,
            is_active=True,
        )
        print(f"[OK] Allowed {user.phone_e164} (id={user.id}, role={user.role})")


def cmd_remove_user(args: argparse.Namespace) -> None:
    init_db()
    with session_scope() as db:
        removed = remove_allowed_user(db, args.phone)
        if removed:
            print(f"[OK] Removed {args.phone} from allowlist.")
        else:
            print(f"[WARN] Phone {args.phone} not found in allowlist.")
            sys.exit(1)


def cmd_list_users(_args: argparse.Namespace) -> None:
    init_db()
    with session_scope() as db:
        users = list_all_users(db)
        if not users:
            print("No users in allowlist yet. Add one with: python cli.py add-user +5511999999999 --admin")
            return
        print(f"{'PHONE (E.164)':<18} {'ROLE':<8} {'ACTIVE':<8} {'TELEGRAM ID':<15} {'GROQ KEY':<12} {'NAME'}")
        print("-" * 80)
        for u in users:
            cred = get_user_credential(db, u.id, provider="groq")
            key_str = f"gsk_••{cred.key_last4}" if cred else "none"
            tg_str = str(u.telegram_user_id) if u.telegram_user_id else "-"
            print(
                f"{u.phone_e164:<18} {u.role:<8} {str(u.is_active):<8} "
                f"{tg_str:<15} {key_str:<12} {u.display_name or '-'}"
            )


def cmd_generate_secrets(_args: argparse.Namespace) -> None:
    fernet_key = Fernet.generate_key().decode("ascii")
    jwt_secret = secrets.token_urlsafe(48)
    webhook_secret = secrets.token_urlsafe(32)
    print("# Copy these into your backend/.env file:")
    print(f"APP_ENCRYPTION_KEY={fernet_key}")
    print(f"JWT_SECRET={jwt_secret}")
    print(f"TELEGRAM_WEBHOOK_SECRET={webhook_secret}")


def main() -> None:
    parser = argparse.ArgumentParser(description="WhAppend allowlist & security CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add-user", help="Add or update an allowed phone number")
    p_add.add_argument("phone", help="Phone number in E.164 format, e.g. +5511999999999")
    p_add.add_argument("--admin", action="store_true", help="Grant admin role")
    p_add.add_argument("--name", default=None, help="Optional display name")
    p_add.set_defaults(func=cmd_add_user)

    p_rm = sub.add_parser("remove-user", help="Remove a phone number from the allowlist")
    p_rm.add_argument("phone", help="Phone number to remove")
    p_rm.set_defaults(func=cmd_remove_user)

    p_ls = sub.add_parser("list-users", help="List all allowed phone numbers")
    p_ls.set_defaults(func=cmd_list_users)

    p_sec = sub.add_parser("generate-secrets", help="Generate APP_ENCRYPTION_KEY and JWT_SECRET")
    p_sec.set_defaults(func=cmd_generate_secrets)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

