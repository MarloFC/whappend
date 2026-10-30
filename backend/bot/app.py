"""
Telegram Bot integration powered by aiogram 3.x.

Supports:
1. Phone number allowlist verification via Telegram's verified "Share Contact" button
   (checking `contact.user_id == message.from_user.id` so contacts cannot be forged).
2. BYOK Groq API key configuration (`/setkey`, `/key`, `/removekey`) with automatic
   deletion of the message containing the raw key and Fernet encryption at rest.
3. Plain LLM chat with persistent per-user history (`/chatmode`, `/clear`).
4. Sending video, audio, voice notes, or photos directly in Telegram for multimodal
   AI analysis, then asking follow-up questions about them.
5. Listing and selecting media uploaded on the web or Telegram (`/videos`, `/select`).
6. Admin allowlist commands (`/admin_add`, `/admin_remove`, `/admin_list`).
"""

import asyncio
import uuid
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)

from config import settings
from core.repositories import (
    append_chat_message,
    clear_chat_history,
    delete_user_groq_key,
    get_decrypted_groq_key,
    get_recent_chat_messages,
    get_user_by_phone,
    get_user_by_telegram_id,
    get_user_credential,
    link_telegram_account,
    list_all_users,
    remove_allowed_user,
    save_user_groq_key,
    upsert_allowed_user,
)
from core.security import mask_key_in_text, normalize_phone, validate_groq_api_key
from db.base import session_scope
from db.models import User
from models.schemas import ChatMessage, VideoRecord, VideoStatus
from routers.videos import process_video
from services.langchain_service import answer_free_chat
from services.rag_service import answer_question
import store

bot_router = Router(name="whappend_bot")

_bot_instance: Optional[Bot] = None
_dp_instance: Optional[Dispatcher] = None
_polling_task: Optional[asyncio.Task] = None


class KeySetupState(StatesGroup):
    waiting_for_groq_key = State()


# ─── Keyboards ────────────────────────────────────────────────────────────────

def _share_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Share my phone number to verify", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="Tap the '📱 Share my phone number' button below ⬇️",
    )


def _media_selection_keyboard(videos: list[VideoRecord], active_id: Optional[str]) -> InlineKeyboardMarkup:
    rows = []
    for v in videos[:10]:
        icon = "🎬" if v.media_type == "video" else "🎙️" if v.media_type == "audio" else "🖼️"
        src_badge = "🌐" if getattr(v, "source", "web") == "web" else "✈️"
        active_mark = "✅ " if v.id == active_id else ""
        label = f"{active_mark}{icon}{src_badge} {v.original_name[:28]} ({v.status.value})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"selmedia:{v.id}")])
    rows.append([InlineKeyboardButton(text="💬 Switch to Free LLM Chat (no media)", callback_data="selmedia:none")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Auth Helper ──────────────────────────────────────────────────────────────

def _get_verified_telegram_user(tg_user_id: int) -> Optional[User]:
    with session_scope() as db:
        user = get_user_by_telegram_id(db, tg_user_id)
        if user and user.is_active:
            return user
        return None


async def _require_verified_user(message: Message) -> Optional[User]:
    if not message.from_user:
        return None
    user = _get_verified_telegram_user(message.from_user.id)
    if not user:
        await message.answer(
            "🔒 <b>Phone verification required</b>\n\n"
            "Only phone numbers on the allowlist can use this bot.\n"
            "• <b>Mobile / Desktop app:</b> tap the <b>📱 Share my phone number</b> button at the bottom of your screen (next to the text input box, or click the <code>⊞</code> keyboard icon).\n"
            "• <b>Telegram Web:</b> send <code>/verify +55YOUR_PHONE</code> (e.g. <code>/verify +5511999999999</code>).",
            reply_markup=_share_contact_keyboard(),
        )
        return None
    return user


# ─── 1. /start & Contact Verification ─────────────────────────────────────────

@bot_router.message(Command("start", "help"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not message.from_user:
        return

    user = _get_verified_telegram_user(message.from_user.id)
    if not user:
        await message.answer(
            "👋 <b>Welcome to WhAppend AI!</b>\n\n"
            "Access is restricted to allowlisted phone numbers, and every user brings their own "
            "Groq API key (<b>BYOK</b>).\n\n"
            "<b>How to verify your phone number:</b>\n"
            "1️⃣ Look at the <b>bottom of your chat bar</b> (below the message input box, or click the <code>⊞</code> keyboard icon on the right of the input bar) and tap <b>📱 Share my phone number to verify</b>.\n"
            "2️⃣ <i>Using Telegram Web in a browser?</i> Send:\n"
            "<code>/verify +55YOUR_NUMBER</code>",
            reply_markup=_share_contact_keyboard(),
        )
        return

    with session_scope() as db:
        cred = get_user_credential(db, user.id, provider="groq")
        has_key = cred is not None
        last4 = cred.key_last4 if cred else None

    key_line = (
        f"✅ <b>Groq Key:</b> <code>gsk_••••{last4}</code>"
        if has_key
        else "⚠️ <b>Groq Key:</b> Not set yet — send /setkey to configure your BYOK key."
    )
    admin_help = (
        "\n\n<b>Admin Commands:</b>\n"
        "• <code>/admin_add +5511999999999 [admin]</code> — allow a phone number\n"
        "• <code>/admin_remove +5511999999999</code> — revoke a phone number\n"
        "• <code>/admin_list</code> — list all allowed numbers"
        if user.role == "admin"
        else ""
    )

    await message.answer(
        f"✨ <b>WhAppend AI Connected</b>\n"
        f"📱 Phone: <code>{user.phone_e164}</code> ({user.role})\n"
        f"{key_line}\n\n"
        f"<b>What you can do:</b>\n"
        f"• 🔑 <code>/setkey</code> — set or update your Groq API key (BYOK)\n"
        f"• 🔍 <code>/key</code> — check your stored key status\n"
        f"• 🗑️ <code>/removekey</code> — delete your stored key\n"
        f"• 🎥 <b>Send any Video, Audio/Voice, or Photo</b> — AI analyzes it & lets you ask questions\n"
        f"• 📂 <code>/videos</code> — pick from media you uploaded on the Web or Telegram\n"
        f"• 💬 <code>/chatmode</code> — switch to general LLM chat (no media context)\n"
        f"• 🧹 <code>/clear</code> — clear current conversation memory"
        f"{admin_help}",
        reply_markup=ReplyKeyboardRemove(),
    )


@bot_router.message(F.contact)
async def handle_contact_verification(message: Message):
    """
    Verifies that:
    1) The shared contact belongs to the sender (`contact.user_id == message.from_user.id`)
    2) The normalized E.164 phone number is in the `users` allowlist table and active.
    """
    if not message.from_user or not message.contact:
        return

    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer(
            "⛔ You must share <b>your own</b> Telegram contact using the button below, "
            "not a forwarded contact card.",
            reply_markup=_share_contact_keyboard(),
        )
        return

    try:
        phone_e164 = normalize_phone(contact.phone_number)
    except ValueError:
        await message.answer("⛔ Could not parse that phone number.")
        return

    with session_scope() as db:
        user = get_user_by_phone(db, phone_e164)
        if not user or not user.is_active:
            await message.answer(
                f"⛔ Sorry, <code>{phone_e164}</code> is not on the allowlist.\n"
                f"Ask the administrator to authorize your number.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        full_name = " ".join(filter(None, [contact.first_name, contact.last_name])) or None
        link_telegram_account(
            db,
            user=user,
            telegram_user_id=message.from_user.id,
            telegram_username=message.from_user.username,
            display_name=full_name,
        )
        cred = get_user_credential(db, user.id, provider="groq")
        has_key = cred is not None

    next_step = (
        "Your Groq API key is already configured! Send any message or media to start."
        if has_key
        else "Next step: send <code>/setkey gsk_your_key_here</code> to configure your personal Groq API key (BYOK)."
    )
    await message.answer(
        f"✅ <b>Phone verified!</b> (<code>{phone_e164}</code>)\n"
        f"Your Telegram account is now linked.\n\n"
        f"{next_step}",
        reply_markup=ReplyKeyboardRemove(),
    )


@bot_router.message(Command("verify"))
async def cmd_verify_phone(message: Message, command: CommandObject):
    """
    Fallback for Telegram Web (where ReplyKeyboard `request_contact` is not rendered):
    Allows `/verify +5511999999999` if that phone is in the allowlist and not yet claimed
    by a different Telegram account.
    """
    if not message.from_user:
        return

    raw_phone = (command.args or "").strip()
    if not raw_phone:
        await message.answer(
            "Usage: <code>/verify +5511999999999</code>\n"
            "<i>(Or tap the <b>📱 Share my phone number</b> button at the bottom of the screen on Telegram Mobile/Desktop.)</i>",
            reply_markup=_share_contact_keyboard(),
        )
        return

    try:
        phone_e164 = normalize_phone(raw_phone)
    except ValueError as exc:
        await message.answer(f"⛔ Invalid phone number format: {exc}")
        return

    with session_scope() as db:
        user = get_user_by_phone(db, phone_e164)
        if not user or not user.is_active:
            await message.answer(
                f"⛔ Sorry, <code>{phone_e164}</code> is not on the allowlist.\n"
                f"Make sure you added it with:\n"
                f"<code>python cli.py add-user {phone_e164} --admin</code>"
            )
            return

        if user.telegram_user_id and user.telegram_user_id != message.from_user.id:
            await message.answer(
                "⛔ This phone number is already linked to another Telegram account."
            )
            return

        full_name = " ".join(filter(None, [message.from_user.first_name, message.from_user.last_name])) or None
        link_telegram_account(
            db,
            user=user,
            telegram_user_id=message.from_user.id,
            telegram_username=message.from_user.username,
            display_name=full_name,
        )
        cred = get_user_credential(db, user.id, provider="groq")
        has_key = cred is not None

    next_step = (
        "Your Groq API key is already configured! Send any message or media to start."
        if has_key
        else "Next step: send <code>/setkey gsk_your_key_here</code> to configure your personal Groq API key (BYOK)."
    )
    await message.answer(
        f"✅ <b>Phone verified!</b> (<code>{phone_e164}</code>)\n"
        f"Your Telegram account (<code>{message.from_user.id}</code>) is now linked.\n\n"
        f"{next_step}",
        reply_markup=ReplyKeyboardRemove(),
    )


# ─── 2. BYOK Groq API Key Commands ────────────────────────────────────────────

@bot_router.message(Command("setkey"))
async def cmd_setkey(message: Message, command: CommandObject, state: FSMContext):
    user = await _require_verified_user(message)
    if not user:
        return

    # Support inline `/setkey gsk_...` or interactive prompt
    arg_key = (command.args or "").strip()
    if arg_key:
        await _process_and_store_groq_key(message, user.id, arg_key, state)
        return

    await state.set_state(KeySetupState.waiting_for_groq_key)
    await message.answer(
        "🔑 <b>Send your Groq API key now</b> (starts with <code>gsk_...</code>).\n\n"
        "• Get a free key at <a href='https://console.groq.com/keys'>console.groq.com/keys</a>\n"
        "• Your message will be <b>automatically deleted</b> from the chat as soon as it is encrypted and saved.\n"
        "• Send /cancel to abort."
    )


@bot_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Cancelled.")


@bot_router.message(KeySetupState.waiting_for_groq_key, F.text)
async def handle_waiting_for_key(message: Message, state: FSMContext):
    user = await _require_verified_user(message)
    if not user:
        await state.clear()
        return
    raw_key = (message.text or "").strip()
    await _process_and_store_groq_key(message, user.id, raw_key, state)


async def _process_and_store_groq_key(
    message: Message,
    user_id: str,
    raw_key: str,
    state: FSMContext,
):
    # Immediately try to delete the user's message containing the plaintext secret
    try:
        await message.delete()
    except Exception:
        pass

    status_msg = await message.answer("🔄 Validating your Groq API key with Groq…")
    valid, error = await asyncio.to_thread(validate_groq_api_key, raw_key)
    if not valid:
        await status_msg.edit_text(
            f"❌ <b>Groq rejected that API key:</b>\n<code>{mask_key_in_text(error or 'Invalid key')}</code>\n\n"
            f"Send /setkey to try again."
        )
        await state.clear()
        return

    with session_scope() as db:
        cred = save_user_groq_key(db, user_id, raw_key)
        last4 = cred.key_last4

    await state.clear()
    await status_msg.edit_text(
        f"✅ <b>Groq API Key Verified & Encrypted!</b>\n"
        f"Stored key: <code>gsk_••••{last4}</code>\n"
        f"<i>(Your plaintext key message was deleted for security.)</i>\n\n"
        f"You can now chat with the AI or send a video, audio note, or photo!"
    )


@bot_router.message(Command("key"))
async def cmd_key_status(message: Message):
    user = await _require_verified_user(message)
    if not user:
        return

    with session_scope() as db:
        cred = get_user_credential(db, user.id, provider="groq")
        if not cred:
            await message.answer(
                "⚠️ <b>No Groq API key configured.</b>\n"
                "Send <code>/setkey</code> to configure your BYOK Groq key."
            )
            return
        validated_str = cred.validated_at.strftime("%Y-%m-%d %H:%M UTC") if cred.validated_at else "unknown"
        await message.answer(
            f"🔑 <b>Your BYOK Groq Key</b>\n"
            f"• Key: <code>gsk_••••{cred.key_last4}</code>\n"
            f"• Validated: <code>{validated_str}</code>\n"
            f"• Model: <code>{settings.groq_llm_model}</code>\n\n"
            f"Use /setkey to replace or /removekey to delete it."
        )


@bot_router.message(Command("removekey"))
async def cmd_remove_key(message: Message):
    user = await _require_verified_user(message)
    if not user:
        return
    with session_scope() as db:
        removed = delete_user_groq_key(db, user.id)
    if removed:
        await message.answer("🗑️ Your Groq API key has been deleted from the database.")
    else:
        await message.answer("You don't have a stored Groq API key.")


# ─── 3. Media Selection (/videos, /chatmode, /clear) ──────────────────────────

@bot_router.message(Command("videos", "media"))
async def cmd_list_videos(message: Message):
    user = await _require_verified_user(message)
    if not user:
        return

    videos = store.list_videos(user_id=user.id)
    if not videos:
        await message.answer(
            "📂 You haven't uploaded any media yet.\n"
            "Send a video, audio/voice note, or photo right here in Telegram, or upload one on the Web UI!"
        )
        return

    await message.answer(
        "📂 <b>Your Media Library (Web & Telegram)</b>\n"
        "Tap any item below to ask questions about it, or switch to free LLM chat:",
        reply_markup=_media_selection_keyboard(videos, user.active_media_id),
    )


@bot_router.callback_query(F.data.startswith("selmedia:"))
async def cb_select_media(callback: CallbackQuery):
    if not callback.from_user or not callback.data:
        return
    user = _get_verified_telegram_user(callback.from_user.id)
    if not user:
        await callback.answer("Please /start and verify your phone first.", show_alert=True)
        return

    target_id = callback.data.split(":", 1)[1]
    with session_scope() as db:
        db_user = db.get(User, user.id)
        if not db_user:
            return
        if target_id == "none":
            db_user.active_media_id = None
            await callback.answer("Switched to Free LLM Chat")
            if callback.message:
                await callback.message.edit_text(
                    "💬 <b>Free LLM Chat Mode active.</b>\n"
                    "Send any message to chat directly with Groq, or use /videos to pick a media item."
                )
            return

        video = store.get_video(target_id, user_id=user.id)
        if not video:
            await callback.answer("Media not found.", show_alert=True)
            return
        db_user.active_media_id = video.id

    events_count = len(store.get_events(video.id))
    await callback.answer("Media selected!")
    if callback.message:
        await callback.message.edit_text(
            f"🎯 <b>Active Media:</b> <code>{video.original_name}</code>\n"
            f"• Type: {video.media_type} ({video.status.value})\n"
            f"• Indexed events: {events_count}\n\n"
            f"Ask any question about this {video.media_type} (prefix with <code>!agent </code> to use Agent Mode),\n"
            f"or send /chatmode to return to general LLM chat."
        )


@bot_router.message(Command("chatmode"))
async def cmd_chatmode(message: Message):
    user = await _require_verified_user(message)
    if not user:
        return
    with session_scope() as db:
        db_user = db.get(User, user.id)
        if db_user:
            db_user.active_media_id = None
    await message.answer(
        "💬 <b>Switched to Free LLM Chat Mode.</b>\n"
        "Your messages now go directly to Groq LLM. Use /videos anytime to query an uploaded video/audio/image."
    )


@bot_router.message(Command("clear"))
async def cmd_clear_history(message: Message):
    user = await _require_verified_user(message)
    if not user:
        return
    with session_scope() as db:
        deleted = clear_chat_history(db, user.id, media_id=user.active_media_id)
    await message.answer(f"🧹 Cleared {deleted} messages from current conversation memory.")


# ─── 4. Admin Allowlist Commands ──────────────────────────────────────────────

@bot_router.message(Command("admin_add"))
async def cmd_admin_add(message: Message, command: CommandObject):
    user = await _require_verified_user(message)
    if not user or user.role != "admin":
        await message.answer("⛔ Admin privileges required.")
        return

    args = (command.args or "").split()
    if not args:
        await message.answer("Usage: <code>/admin_add +5511999999999 [admin|user]</code>")
        return

    raw_phone = args[0]
    role = args[1].lower() if len(args) > 1 and args[1].lower() in ("admin", "user") else "user"
    try:
        with session_scope() as db:
            target = upsert_allowed_user(db, raw_phone=raw_phone, role=role, is_active=True)
            phone_e164 = target.phone_e164
    except ValueError as exc:
        await message.answer(f"❌ Invalid phone number: {exc}")
        return

    await message.answer(f"✅ Added <code>{phone_e164}</code> to the allowlist with role <b>{role}</b>.")


@bot_router.message(Command("admin_remove"))
async def cmd_admin_remove(message: Message, command: CommandObject):
    user = await _require_verified_user(message)
    if not user or user.role != "admin":
        await message.answer("⛔ Admin privileges required.")
        return

    raw_phone = (command.args or "").strip()
    if not raw_phone:
        await message.answer("Usage: <code>/admin_remove +5511999999999</code>")
        return

    try:
        norm = normalize_phone(raw_phone)
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return

    if norm == user.phone_e164:
        await message.answer("⛔ You cannot remove your own admin number.")
        return

    with session_scope() as db:
        removed = remove_allowed_user(db, norm)

    if removed:
        await message.answer(f"🗑️ Removed <code>{norm}</code> from the allowlist.")
    else:
        await message.answer(f"Phone <code>{norm}</code> was not found.")


@bot_router.message(Command("admin_list"))
async def cmd_admin_list(message: Message):
    user = await _require_verified_user(message)
    if not user or user.role != "admin":
        await message.answer("⛔ Admin privileges required.")
        return

    with session_scope() as db:
        users = list_all_users(db)
        lines = []
        for u in users:
            cred = get_user_credential(db, u.id, provider="groq")
            tg_status = f"TG:{u.telegram_user_id}" if u.telegram_user_id else "unlinked"
            key_status = f"key:••••{cred.key_last4}" if cred else "no-key"
            lines.append(f"• <code>{u.phone_e164}</code> [{u.role}] ({tg_status}, {key_status})")

    await message.answer(
        f"📋 <b>Allowed Phone Numbers ({len(lines)}):</b>\n" + "\n".join(lines)
    )


# ─── 5. Media Uploads via Telegram (Video, Audio, Voice, Photo, Document) ─────

@bot_router.message(F.video | F.audio | F.voice | F.photo | F.document)
async def handle_telegram_media(message: Message):
    user = await _require_verified_user(message)
    if not user or not message.bot:
        return

    with session_scope() as db:
        groq_key = get_decrypted_groq_key(db, user.id)
    if not groq_key:
        await message.answer(
            "🔑 <b>Groq API Key Required</b>\n"
            "Before analyzing media, please configure your BYOK Groq API key with <code>/setkey</code>."
        )
        return

    file_id: Optional[str] = None
    original_name: str = "telegram_media"
    media_type: str = "video"
    ext: str = ".mp4"

    if message.video:
        file_id = message.video.file_id
        original_name = message.video.file_name or "telegram_video.mp4"
        ext = Path(original_name).suffix or ".mp4"
        media_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        original_name = message.audio.file_name or "telegram_audio.mp3"
        ext = Path(original_name).suffix or ".mp3"
        media_type = "audio"
    elif message.voice:
        file_id = message.voice.file_id
        original_name = "voice_note.ogg"
        ext = ".ogg"
        media_type = "audio"
    elif message.photo:
        largest = message.photo[-1]
        file_id = largest.file_id
        original_name = "telegram_photo.jpg"
        ext = ".jpg"
        media_type = "image"
    elif message.document:
        mime = (message.document.mime_type or "").lower()
        original_name = message.document.file_name or "document"
        ext = Path(original_name).suffix.lower()
        if mime.startswith("video/") or ext in (".mp4", ".mov", ".webm", ".mkv"):
            media_type = "video"
        elif mime.startswith("audio/") or ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
            media_type = "audio"
        elif mime.startswith("image/") or ext in (".jpg", ".jpeg", ".png", ".webp"):
            media_type = "image"
        else:
            await message.answer("Unsupported document type. Send a Video, Audio, or Image.")
            return
        file_id = message.document.file_id

    if not file_id:
        return

    progress = await message.answer(f"📥 Downloading your {media_type} from Telegram…")

    video_id = str(uuid.uuid4())
    filename = f"{video_id}{ext}"
    dest_path = settings.storage_dir / "videos" / filename

    try:
        tg_file = await message.bot.get_file(file_id)
        await message.bot.download_file(tg_file.file_path, destination=dest_path)
    except Exception as exc:
        await progress.edit_text(f"❌ Could not download file from Telegram: {exc}")
        return

    video = VideoRecord(
        id=video_id,
        user_id=user.id,
        filename=filename,
        original_name=original_name,
        media_type=media_type,
        status=VideoStatus.PENDING,
        source="telegram",
    )
    store.save_video(video, user_id=user.id, source="telegram")

    await progress.edit_text(
        f"⚙️ <b>Analyzing {media_type}</b> (<code>{original_name}</code>) with your Groq key…\n"
        f"<i>I'll message you here as soon as indexing finishes.</i>"
    )

    # Run pipeline in background thread and notify user on completion
    asyncio.create_task(
        _run_media_pipeline_and_notify(
            bot=message.bot,
            chat_id=message.chat.id,
            status_message_id=progress.message_id,
            user_id=user.id,
            video_id=video_id,
            groq_key=groq_key,
            caption_question=(message.caption or "").strip() or None,
        )
    )


async def _run_media_pipeline_and_notify(
    bot: Bot,
    chat_id: int,
    status_message_id: int,
    user_id: str,
    video_id: str,
    groq_key: str,
    caption_question: Optional[str] = None,
):
    await asyncio.to_thread(process_video, video_id, groq_key)
    video = store.get_video(video_id, user_id=user_id)
    if not video or video.status != VideoStatus.COMPLETED:
        err = video.error if video else "Unknown error"
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"❌ <b>Analysis failed:</b> <code>{mask_key_in_text(err or '')}</code>",
        )
        return

    events = store.get_events(video_id)
    with session_scope() as db:
        db_user = db.get(User, user_id)
        if db_user:
            db_user.active_media_id = video_id

    preview_lines = [
        f"• <code>[{e.timestamp:.1f}s]</code> {e.description[:90]}"
        for e in events[:4]
    ]
    preview_block = "\n".join(preview_lines) if preview_lines else "No events extracted."

    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=status_message_id,
        text=(
            f"✅ <b>{video.media_type.capitalize()} Ready!</b> (<code>{video.original_name}</code>)\n"
            f"• Extracted <b>{len(events)}</b> timeline events\n\n"
            f"<b>Sample highlights:</b>\n{preview_block}\n\n"
            f"💬 <b>Now just send any question</b> to ask about this {video.media_type} "
            f"(or send /chatmode for general chat)."
        ),
    )

    if caption_question:
        res = await asyncio.to_thread(
            answer_question,
            video_id=video_id,
            question=caption_question,
            all_events=events,
            groq_api_key=groq_key,
        )
        await bot.send_message(
            chat_id=chat_id,
            text=f"💡 <b>Answer to your caption:</b>\n\n{res.answer}",
        )


# ─── 6. Text Chat (Media RAG Q&A or Free Conversational LLM) ──────────────────

@bot_router.message(F.text)
async def handle_text_chat(message: Message):
    user = await _require_verified_user(message)
    if not user or not message.text:
        return

    text = message.text.strip()
    if not text:
        return

    with session_scope() as db:
        groq_key = get_decrypted_groq_key(db, user.id)
    if not groq_key:
        await message.answer(
            "🔑 <b>No Groq API key configured yet.</b>\n"
            "Send <code>/setkey</code> to configure your BYOK Groq key first."
        )
        return

    use_agent = False
    if text.lower().startswith("!agent "):
        use_agent = True
        text = text[7:].strip()

    # Load recent chat history for this context
    with session_scope() as db:
        recent_rows = get_recent_chat_messages(
            db, user_id=user.id, media_id=user.active_media_id, limit=10
        )
        history = [ChatMessage(role=r.role, content=r.content) for r in recent_rows]

    # Branch A: User has an active media selected → RAG / Agent Q&A over that media
    if user.active_media_id:
        video = store.get_video(user.active_media_id, user_id=user.id)
        events = store.get_events(user.active_media_id) if video else []
        if video and video.status == VideoStatus.COMPLETED and events:
            thinking = await message.answer(
                f"🔎 Searching <code>{video.original_name}</code>…"
            )
            try:
                res = await asyncio.to_thread(
                    answer_question,
                    video_id=video.id,
                    question=text,
                    all_events=events,
                    groq_api_key=groq_key,
                    history=history,
                    use_agent=use_agent,
                )
                with session_scope() as db:
                    append_chat_message(db, user.id, "user", text, media_id=video.id)
                    append_chat_message(db, user.id, "assistant", res.answer, media_id=video.id)

                await thinking.edit_text(
                    f"🎬 <b>[{video.original_name}]</b>\n\n{res.answer}"
                )
                return
            except Exception as exc:
                await thinking.edit_text(
                    f"❌ Error querying media with Groq: <code>{mask_key_in_text(str(exc))}</code>"
                )
                return

    # Branch B: Free conversational LLM chat using user's Groq key
    thinking = await message.answer("💭 Thinking…")
    try:
        reply = await asyncio.to_thread(
            answer_free_chat,
            question=text,
            history=history,
            groq_api_key=groq_key,
        )
        with session_scope() as db:
            append_chat_message(db, user.id, "user", text, media_id=None)
            append_chat_message(db, user.id, "assistant", reply, media_id=None)

        await thinking.edit_text(reply)
    except Exception as exc:
        await thinking.edit_text(
            f"❌ Groq error: <code>{mask_key_in_text(str(exc))}</code>"
        )


# ─── Bot Lifecycle (Webhook or Long-Polling) & Outbound Helper ────────────────

def get_bot_and_dispatcher() -> tuple[Optional[Bot], Optional[Dispatcher]]:
    global _bot_instance, _dp_instance
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        return None, None
    if _bot_instance is None:
        _bot_instance = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        _dp_instance = Dispatcher(storage=MemoryStorage())
        _dp_instance.include_router(bot_router)
    return _bot_instance, _dp_instance


async def send_telegram_text(chat_id: int, text: str) -> bool:
    """Used by the web OTP endpoint to push a 6-digit login code via the Telegram bot."""
    bot, _ = get_bot_and_dispatcher()
    if not bot:
        return False
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except Exception as exc:
        print(f"[TelegramBot] Failed to send message to {chat_id}: {exc}")
        return False


async def start_bot_lifecycle() -> None:
    """Starts webhook registration (if TELEGRAM_WEBHOOK_URL set) or background long-polling."""
    global _polling_task
    bot, dp = get_bot_and_dispatcher()
    if not bot or not dp:
        print("[TelegramBot] TELEGRAM_BOT_TOKEN not configured — Telegram bot disabled.")
        return

    webhook_base = (settings.telegram_webhook_url or "").strip().rstrip("/")
    if webhook_base:
        webhook_url = f"{webhook_base}/telegram/webhook"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=(settings.telegram_webhook_secret or None),
            drop_pending_updates=True,
        )
        print(f"[TelegramBot] Webhook registered at {webhook_url}")
    else:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            me = await bot.get_me()
            print(f"[TelegramBot] Starting long-polling for @{me.username}…")
            _polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        except Exception as exc:
            print(f"[TelegramBot] Could not start polling ({exc}). Check TELEGRAM_BOT_TOKEN.")


async def stop_bot_lifecycle() -> None:
    global _polling_task
    bot, dp = get_bot_and_dispatcher()
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
    if bot:
        await bot.session.close()


async def process_webhook_update(payload: dict) -> None:
    bot, dp = get_bot_and_dispatcher()
    if not bot or not dp:
        return
    update = Update.model_validate(payload, context={"bot": bot})
    await dp.feed_update(bot, update)

