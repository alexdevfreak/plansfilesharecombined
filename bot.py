import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

"""
Premium Paid Media Bot — Manual Authorization Flow
=================================================

• Admin grants access manually: /authorize <user_id> <duration>
  - duration supports: 1d, 7d, 14d, 1m, 3m, 6m, 1y, 2y, life|lifetime
• Users see 4 categories (CT1..CT4) → each has 3 sub-niches (ICT1..ICT3)
• Inside each ICT: [ Get Video | Next Video | Go Back ]
  - Get Video  → random unseen video
  - Next Video → next sequential video
  - Videos are copied from private database channels defined in DB_CHANNELS
• Bot tracks per-user progress per subcategory; videos auto-delete after N seconds
• Stylish inline menus + profile screen

Requirements:
- pyrogram, tgcrypto
- Create a Bot via @BotFather and put BOT_TOKEN below
- Make the bot an ADMIN in every database channel in DB_CHANNELS

Environment variables (recommended):
- API_ID, API_HASH, BOT_TOKEN
- ADMINS: comma-separated Telegram user IDs (e.g., "123,456")
- SUPPORT_URL (optional): t.me/your_support

Replace the DB_CHANNELS mapping with your actual channel IDs (negative integers).
"""

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
API_ID: int = int(os.getenv("API_ID", "123456"))
API_HASH: str = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "your_bot_token")

# Allow multiple admins
_admins_env = os.getenv("ADMINS", "123456789")
ADMINS = {int(x.strip()) for x in _admins_env.split(',') if x.strip().isdigit()}

SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/your_support")
AUTO_DELETE_SECONDS: int = int(os.getenv("AUTO_DELETE_SECONDS", "3600"))  # 1 hour default

DB_FILE = os.getenv("DB_FILE", "db.json")

# Map "CTx-ICTy" -> private channel id (int). Fill with *your* private channel IDs.
DB_CHANNELS: Dict[str, int] = {
    "CT1-ICT1": -1001111111111,
    "CT1-ICT2": -1001111111112,
    "CT1-ICT3": -1001111111113,
    "CT2-ICT1": -1001111111114,
    "CT2-ICT2": -1001111111115,
    "CT2-ICT3": -1001111111116,
    "CT3-ICT1": -1001111111117,
    "CT3-ICT2": -1001111111118,
    "CT3-ICT3": -1001111111119,
    "CT4-ICT1": -1001111111120,
    "CT4-ICT2": -1001111111121,
    "CT4-ICT3": -1001111111122,
}

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────
app = Client("premium_paid_media_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ─────────────────────────────────────────────────────────────────────────────
# DB Helpers
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_DB: Dict[str, Any] = {
    "users": [],              # list of user IDs who started the bot
    "premium": {},            # user_id(str) -> iso expiry or "life"
    "progress": {},           # user_id(str) -> { "CTx-ICTy": {"seen": [msg_ids], "last_index": int} }
}


def load_db() -> Dict[str, Any]:
    if not os.path.exists(DB_FILE):
        save_db(DEFAULT_DB)
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(DEFAULT_DB))


def save_db(d: Dict[str, Any]) -> None:
    with open(DB_FILE, 'w') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


db = load_db()

# ─────────────────────────────────────────────────────────────────────────────
# Premium Helpers
# ─────────────────────────────────────────────────────────────────────────────
DURATION_MAP = {
    "1d": 1,
    "7d": 7,
    "14d": 14,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "2y": 730,
}


def set_premium(user_id: int, duration: str) -> None:
    key = str(user_id)
    if duration.lower() in ("life", "lifetime", "forever"):
        db.setdefault("premium", {})[key] = "life"
    else:
        days = DURATION_MAP.get(duration.lower())
        if not days:
            # Fallback: try to parse like "10d" or "45d"
            if duration.lower().endswith('d') and duration[:-1].isdigit():
                days = int(duration[:-1])
            else:
                days = 30  # default 30 days
        db.setdefault("premium", {})[key] = (datetime.utcnow() + timedelta(days=days)).isoformat()
    save_db(db)


def remove_premium(user_id: int) -> None:
    db.setdefault("premium", {}).pop(str(user_id), None)
    save_db(db)


def is_premium(user_id: int) -> bool:
    val = db.get("premium", {}).get(str(user_id))
    if not val:
        return False
    if val == "life":
        return True
    try:
        return datetime.fromisoformat(val) > datetime.utcnow()
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Keyboards (Stylish)
# ─────────────────────────────────────────────────────────────────────────────

def splash_plans_keyboard() -> InlineKeyboardMarkup:
    # Only to redirect to support since we use manual authorization
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💳 Buy Premium (DM)", url=SUPPORT_URL)],
            [InlineKeyboardButton("ℹ️ How to get access", callback_data="how_access")],
        ]
    )


def main_categories_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Ⅰ  📂 CT1", callback_data="cat_CT1"),
             InlineKeyboardButton("Ⅱ  📂 CT2", callback_data="cat_CT2")],
            [InlineKeyboardButton("Ⅲ 📂 CT3", callback_data="cat_CT3"),
             InlineKeyboardButton("Ⅳ 📂 CT4", callback_data="cat_CT4")],
            [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        ]
    )


def ict_kb(cat_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Ⅰ 🎭 ICT1", callback_data=f"sub_{cat_key}_ICT1"),
             InlineKeyboardButton("Ⅱ 🎶 ICT2", callback_data=f"sub_{cat_key}_ICT2")],
            [InlineKeyboardButton("Ⅲ 🎥 ICT3", callback_data=f"sub_{cat_key}_ICT3")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
        ]
    )


def media_actions_kb(cat_key: str, ict_key: str) -> InlineKeyboardMarkup:
    key = f"{cat_key}-{ict_key}"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶️ Get Video", callback_data=f"get_{key}"),
             InlineKeyboardButton("⏭ Next Video", callback_data=f"next_{key}")],
            [InlineKeyboardButton("🔙 Go Back", callback_data=f"back_{cat_key}")],
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Utilities: Channel Index & Sending
# ─────────────────────────────────────────────────────────────────────────────
channel_cache: Dict[str, List[int]] = {}


async def build_channel_cache(channel_key: str) -> List[int]:
    """Load media message IDs from a private channel and cache them (oldest → newest)."""
    if channel_key in channel_cache and channel_cache[channel_key]:
        return channel_cache[channel_key]

    channel_id = DB_CHANNELS.get(channel_key)
    if not channel_id:
        channel_cache[channel_key] = []
        return []

    ids: List[int] = []
    try:
        async for m in app.get_chat_history(chat_id=channel_id, limit=2000):
            # Consider common media types; adjust as needed
            if m.video or m.document or m.animation or m.photo:
                ids.append(m.id)
    except Exception:
        pass

    ids.sort()
    channel_cache[channel_key] = ids
    return ids


async def pick_message_id_for_user(user_id: int, channel_key: str, mode: str) -> Optional[int]:
    """Return a message_id based on mode (random/next) and user progress; update progress."""
    ids = await build_channel_cache(channel_key)
    if not ids:
        return None

    # Ensure progress structure
    ukey = str(user_id)
    user_prog = db.setdefault("progress", {}).setdefault(ukey, {})
    prog = user_prog.setdefault(channel_key, {"seen": [], "last_index": -1})

    seen_set = set(prog.get("seen", []))
    available = [mid for mid in ids if mid not in seen_set]
    if not available:
        # reset if user watched everything
        prog["seen"] = []
        prog["last_index"] = -1
        available = ids.copy()

    if mode == "next":
        # sequential based on sorted order
        last_index = prog.get("last_index", -1) + 1
        if last_index >= len(ids):
            last_index = 0
        chosen = ids[last_index]
        prog["last_index"] = last_index
    else:
        # random unseen
        chosen = random.choice(available)
        # keep last_index aligned to position of chosen (optional)
        try:
            prog["last_index"] = ids.index(chosen)
        except ValueError:
            pass

    # mark seen
    if chosen not in prog["seen"]:
        prog["seen"].append(chosen)

    save_db(db)
    return chosen


async def send_and_autodelete(to_chat_id: int, from_chat_id: int, msg_id: int) -> None:
    try:
        sent = await app.copy_message(to_chat_id, from_chat_id, msg_id)
    except Exception as e:
        try:
            await app.send_message(to_chat_id, f"⚠️ Failed to send media: {e}")
        except Exception:
            pass
        return

    # schedule delete
    async def _delay_delete(chat_id: int, message_id: int, delay: int):
        await asyncio.sleep(delay)
        try:
            await app.delete_messages(chat_id, message_id)
        except Exception:
            pass

    asyncio.create_task(_delay_delete(to_chat_id, sent.id, AUTO_DELETE_SECONDS))


# ─────────────────────────────────────────────────────────────────────────────
# Guards & Common Replies
# ─────────────────────────────────────────────────────────────────────────────
async def require_premium(cb: CallbackQuery) -> bool:
    if is_premium(cb.from_user.id):
        return True
    await cb.answer("Premium required.", show_alert=True)
    await cb.message.reply_text(
        "🔒 *Premium Only*\n\nContact support to get access.",
        reply_markup=splash_plans_keyboard(),
        disable_web_page_preview=True,
    )
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Commands — Public
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(_, m: Message):
    uid = m.from_user.id
    if uid not in db.get("users", []):
        db.setdefault("users", []).append(uid)
        save_db(db)

    if is_premium(uid):
        await m.reply_text(
            """
✨ *WELCOME BACK — PREMIUM* ✨

Choose a category:
            """.strip(),
            reply_markup=main_categories_kb(),
            disable_web_page_preview=True,
        )
    else:
        await m.reply_text(
            """
👋 *Welcome to VIP Media Bot*

This is a paid bot (premium-only). Get access from support below:
            """.strip(),
            reply_markup=splash_plans_keyboard(),
            disable_web_page_preview=True,
        )


@app.on_message(filters.command("profile") & filters.private)
async def profile_cmd(_, m: Message):
    uid = m.from_user.id
    if not is_premium(uid):
        return await m.reply_text(
            "🔒 *Premium Only*\n\nContact support to get access.",
            reply_markup=splash_plans_keyboard(),
        )
    val = db.get("premium", {}).get(str(uid))
    expiry_text = "Lifetime" if val == "life" else (val.split('T')[0] if val else "-")
    await m.reply_text(
        f"""
👤 *Profile*

🆔 ID: `{uid}`
💎 Status: *Premium*
📅 Valid Till: *{expiry_text}*
        """.strip(),
        reply_markup=main_categories_kb(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Commands — Admin
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("authorize"))
async def authorize_cmd(_, m: Message):
    if m.from_user.id not in ADMINS:
        return await m.reply_text("❌ Not authorized.")

    parts = m.text.split()
    if len(parts) != 3:
        return await m.reply_text("Usage: /authorize <user_id> <1d|7d|1m|3m|6m|1y|2y|life>")

    try:
        user_id = int(parts[1])
    except ValueError:
        return await m.reply_text("❌ Invalid user id.")

    duration = parts[2]
    set_premium(user_id, duration)

    try:
        val = db["premium"][str(user_id)]
        if val == "life":
            msg = "🎉 Your *Lifetime Premium* has been activated!"
        else:
            msg = f"🎉 Your *Premium* has been activated.\n🗓 Valid till: *{val.split('T')[0]}*"
        await app.send_message(user_id, msg)
    except Exception:
        pass

    await m.reply_text(f"✅ Authorized `{user_id}` for *{duration}*.")


@app.on_message(filters.command("unauthorize"))
async def unauthorize_cmd(_, m: Message):
    if m.from_user.id not in ADMINS:
        return await m.reply_text("❌ Not authorized.")

    parts = m.text.split()
    if len(parts) != 2:
        return await m.reply_text("Usage: /unauthorize <user_id>")

    try:
        user_id = int(parts[1])
    except ValueError:
        return await m.reply_text("❌ Invalid user id.")

    remove_premium(user_id)
    await m.reply_text(f"✅ Removed premium for `{user_id}`.")
    try:
        await app.send_message(user_id, "⚠ Your premium access has been removed by Admin.")
    except Exception:
        pass


@app.on_message(filters.command("authorized"))
async def authorized_cmd(_, m: Message):
    if m.from_user.id not in ADMINS:
        return await m.reply_text("❌ Not authorized.")

    prem = db.get("premium", {})
    if not prem:
        return await m.reply_text("No authorized users.")

    lines = ["📋 *Authorized Users:*\n"]
    for uid, val in prem.items():
        if val == "life":
            lines.append(f"• `{uid}` — Lifetime")
        else:
            try:
                d = datetime.fromisoformat(val)
                lines.append(f"• `{uid}` — until {d.date().isoformat()}")
            except Exception:
                lines.append(f"• `{uid}` — invalid date")
    await m.reply_text("\n".join(lines))


@app.on_message(filters.command("users"))
async def users_cmd(_, m: Message):
    if m.from_user.id not in ADMINS:
        return await m.reply_text("❌ Not authorized.")

    total = len(db.get("users", []))
    premium_cnt = len(db.get("premium", {}))
    await m.reply_text(f"📊 Users: {total}\n💎 Premium: {premium_cnt}")


# ─────────────────────────────────────────────────────────────────────────────
# Callback Flow — Premium Only Content
# ─────────────────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^profile$"))
async def profile_cb(_, cb: CallbackQuery):
    if not await require_premium(cb):
        return
    uid = cb.from_user.id
    val = db.get("premium", {}).get(str(uid))
    expiry_text = "Lifetime" if val == "life" else (val.split('T')[0] if val else '-')
    await cb.answer()
    await cb.message.reply_text(
        f"""
👤 *Profile*

🆔 ID: `{uid}`
💎 Status: *Premium*
📅 Valid Till: *{expiry_text}*
        """.strip(),
        reply_markup=main_categories_kb(),
    )


@app.on_callback_query(filters.regex(r"^cat_CT[1-4]$"))
async def cat_cb(_, cb: CallbackQuery):
    if not await require_premium(cb):
        return
    cat_key = cb.data.split("_")[1]  # CT1..CT4
    await cb.answer()
    await cb.message.reply_text(
        f"📂 *{cat_key}* selected. Choose a subcategory:",
        reply_markup=ict_kb(cat_key),
    )


@app.on_callback_query(filters.regex(r"^sub_CT[1-4]_ICT[1-3]$"))
async def sub_cb(_, cb: CallbackQuery):
    if not await require_premium(cb):
        return
    _, cat, ict = cb.data.split("_")  # [sub, CTx, ICTy]
    await cb.answer()
    await cb.message.reply_text(
        f"{cat} → {ict}\nChoose action:",
        reply_markup=media_actions_kb(cat, ict),
    )


@app.on_callback_query(filters.regex(r"^back_CT[1-4]$"))
async def back_cat_cb(_, cb: CallbackQuery):
    if not await require_premium(cb):
        return
    await cb.answer()
    cat_key = cb.data.split("_")[1]
    await cb.message.reply_text("🔙 Back to subcategories:", reply_markup=ict_kb(cat_key))


@app.on_callback_query(filters.regex(r"^back_main$"))
async def back_main_cb(_, cb: CallbackQuery):
    if not await require_premium(cb):
        return
    await cb.answer()
    await cb.message.reply_text("🏠 Main menu:", reply_markup=main_categories_kb())


@app.on_callback_query(filters.regex(r"^(get|next)_CT[1-4]-ICT[1-3]$"))
async def get_next_cb(_, cb: CallbackQuery):
    if not await require_premium(cb):
        return
    parts = cb.data.split("_")
    mode = parts[0]          # get | next
    channel_key = parts[1]   # CTx-ICTy
    await cb.answer()

    channel_id = DB_CHANNELS.get(channel_key)
    if not channel_id:
        return await cb.message.reply_text("⚠️ This subcategory is not configured yet.")

    msg_id = await pick_message_id_for_user(cb.from_user.id, channel_key, mode=("next" if mode == "next" else "random"))
    if not msg_id:
        return await cb.message.reply_text("❌ No media found in this subcategory.")

    await cb.message.reply_text("✅ Enjoy — this video will auto-delete after 1 hour.")
    await send_and_autodelete(cb.message.chat.id, channel_id, msg_id)


# ─────────────────────────────────────────────────────────────────────────────
# Extra: Info Callback
# ─────────────────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^how_access$"))
async def how_access_cb(_, cb: CallbackQuery):
    await cb.answer()
    await cb.message.reply_text(
        """
💡 *How to get Premium Access*
1) DM the admin using the button above
2) Complete the payment
3) Admin will authorize you with a command (no waiting forms)
4) Come back here and tap /start — you’ll see the categories
        """.strip(),
        disable_web_page_preview=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 Premium Paid Media Bot — starting...")
    app.run()
