# bot.py
# Premium Media Bot — Reply Keyboard Menu version (fixed & styled)
# Requirements: pyrogram, tgcrypto
# Replace placeholders (API_ID, API_HASH, BOT_TOKEN, ADMINS, DB_CHANNELS) before running.

import os
import json
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# ================== CONFIG - EDIT THESE ==================
API_ID = int(os.getenv("API_ID", "123456"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")

# Comma separated admin IDs or single id: "12345,67890"
ADMINS = {int(x.strip()) for x in os.getenv("ADMINS", "123456789").split(",") if x.strip().isdigit()}

DB_FILE = os.getenv("DB_FILE", "db.json")
AUTO_DELETE_SECONDS = int(os.getenv("AUTO_DELETE_SECONDS", "3600"))  # 1 hour default
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/your_support")  # for contact / instructions
# ========================================================

# Map CT -> ICT -> channel_id (use numeric -100... values). Replace with your real private channel IDs.
DB_CHANNELS: Dict[str, Dict[str, int]] = {
    "CT1": {"ICT1": -1001111111111, "ICT2": -1001111111112, "ICT3": -1001111111113},
    "CT2": {"ICT1": -1002222222221, "ICT2": -1002222222222, "ICT3": -1002222222223},
    "CT3": {"ICT1": -1003333333331, "ICT2": -1003333333332, "ICT3": -1003333333333},
    "CT4": {"ICT1": -1004444444441, "ICT2": -1004444444442, "ICT3": -1004444444443},
}

# ----------------- APP -----------------
app = Client("premium_media_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ----------------- DB -----------------
DEFAULT_DB = {
    "users": {},       # user_id (str) -> {"expiry": iso_str or "life"}
    "progress": {},    # user_id (str) -> { "CT1-ICT1": {"seen": [msg_ids], "last_index": int}, ... }
}

def load_db() -> Dict:
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump(DEFAULT_DB, f, indent=2)
        return json.loads(json.dumps(DEFAULT_DB))
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(DEFAULT_DB))

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

db = load_db()

# ----------------- Utilities -----------------
def now_utc() -> datetime:
    return datetime.utcnow()

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def set_premium(user_id: int, duration: str) -> None:
    """duration: 'life' or ISO short like '1d','7d','1m','1y' or numeric days '10d'"""
    key = str(user_id)
    duration = duration.lower()
    if duration in ("life", "lifetime", "forever"):
        db["users"][key] = {"expiry": "life"}
    else:
        # support d/m/y shorthand
        try:
            if duration.endswith("d"):
                days = int(duration[:-1])
            elif duration.endswith("m"):
                days = 30 * int(duration[:-1])
            elif duration.endswith("y"):
                days = 365 * int(duration[:-1])
            else:
                days = int(duration)  # fallback as days
        except Exception:
            days = 30
        expiry = (now_utc() + timedelta(days=days)).isoformat()
        db["users"][key] = {"expiry": expiry}
    save_db()

def remove_premium(user_id: int) -> None:
    db["users"].pop(str(user_id), None)
    save_db()

def is_premium(user_id: int) -> bool:
    rec = db.get("users", {}).get(str(user_id))
    if not rec:
        return False
    val = rec.get("expiry")
    if val == "life":
        return True
    try:
        return datetime.fromisoformat(val) > now_utc()
    except Exception:
        return False

# ----------------- Reply Keyboards (persistent) -----------------
MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📂 CT1"), KeyboardButton("📂 CT2")],
        [KeyboardButton("📂 CT3"), KeyboardButton("📂 CT4")],
        [KeyboardButton("🧾 Profile"), KeyboardButton("ℹ️ How to get access")],
    ],
    resize_keyboard=True,
)

def ct_keyboard(ct_key: str):
    # e.g. "CT1" -> shows "🎞 CT1 - ICT1" etc.
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(f"🎞 {ct_key} - ICT1"), KeyboardButton(f"🎞 {ct_key} - ICT2"), KeyboardButton(f"🎞 {ct_key} - ICT3")],
            [KeyboardButton("🔙 Back to Main")],
        ],
        resize_keyboard=True,
    )

ICT_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("▶️ Get Video")],
        [KeyboardButton("⏭ Next Video")],
        [KeyboardButton("🔙 Back")],
    ],
    resize_keyboard=True,
)

# ----------------- Channel cache -----------------
# caches list of media message ids per "CT-ICT" key (oldest->newest)
channel_cache: Dict[str, List[int]] = {}

async def build_channel_cache(channel_key: str) -> List[int]:
    """Load media message IDs from the channel and cache them."""
    if channel_key in channel_cache and channel_cache[channel_key]:
        return channel_cache[channel_key]

    # channel_key like "CT1-ICT1"
    parts = channel_key.split("-")
    if len(parts) != 2:
        channel_cache[channel_key] = []
        return []

    ct, ict = parts
    channel_id = DB_CHANNELS.get(ct, {}).get(ict)
    if not channel_id:
        channel_cache[channel_key] = []
        return []

    ids: List[int] = []
    try:
        async for m in app.iter_history(channel_id, limit=2000):
            # accept common media types
            if m.video or m.document or m.animation or m.photo:
                ids.append(m.message_id if hasattr(m, "message_id") else m.id)
    except Exception:
        # likely ChannelInvalid or bot not in channel
        ids = []
    ids.sort()
    channel_cache[channel_key] = ids
    return ids

async def pick_message_id_for_user(user_id: int, channel_key: str, mode: str = "random") -> Optional[int]:
    """
    mode = "random" or "next".
    updates db['progress'] for the user.
    """
    ids = await build_channel_cache(channel_key)
    if not ids:
        return None

    ukey = str(user_id)
    user_prog = db.setdefault("progress", {}).setdefault(ukey, {})
    prog = user_prog.setdefault(channel_key, {"seen": [], "last_index": -1})

    seen = set(prog.get("seen", []))
    available = [mid for mid in ids if mid not in seen]

    # If nothing available, reset seen (so they can watch again)
    if not available:
        prog["seen"] = []
        prog["last_index"] = -1
        available = ids.copy()

    if mode == "next":
        last_index = prog.get("last_index", -1) + 1
        if last_index >= len(ids):
            last_index = 0
        chosen = ids[last_index]
        prog["last_index"] = last_index
    else:
        chosen = random.choice(available)
        # align last_index (best effort)
        try:
            prog["last_index"] = ids.index(chosen)
        except Exception:
            pass

    if chosen not in prog["seen"]:
        prog["seen"].append(chosen)

    save_db()
    return chosen

async def send_and_autodelete(to_chat_id: int, from_chat_id: int, msg_id: int):
    """Copy message to user and schedule deletion after AUTO_DELETE_SECONDS."""
    try:
        sent = await app.copy_message(to_chat_id, from_chat_id, msg_id)
    except Exception as e:
        # send fallback error message
        try:
            await app.send_message(to_chat_id, f"⚠️ Failed to send media: {e}")
        except Exception:
            pass
        return

    async def _del_later(chat_id: int, message_id: int, delay: int):
        await asyncio.sleep(delay)
        try:
            await app.delete_messages(chat_id, message_id)
        except Exception:
            pass

    asyncio.create_task(_del_later(to_chat_id, sent.message_id if hasattr(sent, "message_id") else sent.id, AUTO_DELETE_SECONDS))

# ----------------- Commands -----------------
@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    uid = m.from_user.id
    # Ensure user exists in DB (no premium by default)
    if str(uid) not in db.get("users", {}):
        db.setdefault("users", {})[str(uid)] = {"expiry": None}
        save_db()
    text = (
        "✨ *WELCOME TO PREMIUM MEDIA BOT* ✨\n\n"
        "Use the bottom menu to navigate categories.\n"
        "You must be authorized (admin) to access content."
    )
    await m.reply(text, reply_markup=MAIN_MENU)

@app.on_message(filters.command("help") & filters.private)
async def cmd_help(_, m: Message):
    await m.reply(
        "ℹ️ *How this bot works*\n"
        "- Admins authorize users with `/authorize <user_id> <1d|1m|1y|life>`\n"
        "- After authorized: use menu -> CT1..CT4 -> ICT -> Get/Next\n        ",
        reply_markup=MAIN_MENU
    )

@app.on_message(filters.command("profile") & filters.private)
async def cmd_profile(_, m: Message):
    uid = m.from_user.id
    rec = db.get("users", {}).get(str(uid))
    if not rec or not rec.get("expiry"):
        return await m.reply("❌ You are not authorized. Contact support.", reply_markup=MAIN_MENU)
    exp = rec["expiry"]
    exp_text = "Lifetime" if exp == "life" else exp.split("T")[0]
    await m.reply(f"👤 Profile\nID: `{uid}`\nStatus: Premium ✅\nValid till: {exp_text}", reply_markup=MAIN_MENU)

# Admin commands
@app.on_message(filters.command("authorize") & filters.user(lambda _, __, m: m.from_user.id in ADMINS))
async def cmd_authorize(_, m: Message):
    # Usage: /authorize <user_id> <1d|7d|1m|1y|life>
    args = m.text.split()
    if len(args) != 3:
        return await m.reply("Usage: /authorize <user_id> <1d|7d|1m|1y|life>")
    try:
        user_id = int(args[1])
        duration = args[2]
        set_premium(user_id, duration)
        # notify user
        try:
            rec = db["users"].get(str(user_id))
            val = rec.get("expiry")
            if val == "life":
                await app.send_message(user_id, "🎉 You have been granted *Lifetime Premium*!")
            else:
                await app.send_message(user_id, f"🎉 You have been granted Premium until {val.split('T')[0]}")
        except Exception:
            pass
        await m.reply(f"✅ Authorized {user_id} for {duration}")
    except Exception as e:
        await m.reply(f"❌ Error: {e}\nUsage: /authorize <user_id> <1d|7d|1m|1y|life>")

@app.on_message(filters.command("unauthorize") & filters.user(lambda _, __, m: m.from_user.id in ADMINS))
async def cmd_unauthorize(_, m: Message):
    args = m.text.split()
    if len(args) != 2:
        return await m.reply("Usage: /unauthorize <user_id>")
    try:
        user_id = int(args[1])
        remove_premium(user_id)
        await m.reply(f"✅ Removed premium for {user_id}")
        try:
            await app.send_message(user_id, "⚠️ Your premium access has been removed by admin.")
        except Exception:
            pass
    except Exception as e:
        await m.reply(f"❌ Error: {e}")

@app.on_message(filters.command("authorized") & filters.user(lambda _, __, m: m.from_user.id in ADMINS))
async def cmd_authorized(_, m: Message):
    prem = db.get("users", {})
    lines = ["📋 Authorized users:"]
    for uid, info in prem.items():
        val = info.get("expiry")
        if not val:
            continue
        if val == "life":
            lines.append(f"• `{uid}` — Lifetime")
        else:
            try:
                lines.append(f"• `{uid}` — until {val.split('T')[0]}")
            except Exception:
                lines.append(f"• `{uid}` — {val}")
    if len(lines) == 1:
        await m.reply("No authorized users.")
    else:
        await m.reply("\n".join(lines))

@app.on_message(filters.command("users") & filters.user(lambda _, __, m: m.from_user.id in ADMINS))
async def cmd_users(_, m: Message):
    total = len(db.get("users", {}))
    premium_cnt = sum(1 for v in db.get("users", {}).values() if v.get("expiry"))
    await m.reply(f"📊 Users: {total}\n💎 Premium: {premium_cnt}")

# ----------------- Menu (reply keyboard) processing -----------------
@app.on_message(filters.text & filters.private)
async def menu_handler(_, m: Message):
    uid = m.from_user.id
    text = m.text.strip()

    # Help-ish shortcut
    if text in ("ℹ️ How to get access", "How to get access", "/how"):
        return await m.reply(
            "💡 How to get Premium Access:\n"
            f"1) Contact support/admin: {SUPPORT_URL}\n"
            "2) Pay the admin\n"
            "3) Admin runs: /authorize <your_id> <1m|1y|life>\n"
            "4) Come back and press /start",
            reply_markup=MAIN_MENU
        )

    # Profile button
    if text == "🧾 Profile":
        return await cmd_profile(_, m)

    # If user is not premium, block content buttons
    if not is_premium(uid):
        # Allow admins to use CT menus even if not authorized
        if not is_admin(uid):
            return await m.reply("🚫 You are not authorized. Contact admin to get access.", reply_markup=MAIN_MENU)

    # MAIN CATEGORY pressed
    if text in ("📂 CT1", "📂 CT2", "📂 CT3", "📂 CT4"):
        ct = text.split()[1]
        # initialize progress for this user if not exists
        db.setdefault("progress", {}).setdefault(str(uid), {})
        # store current CT under a session key
        db["progress"].setdefault(str(uid), {}).setdefault("_session", {})["ct"] = ct
        db["progress"].setdefault(str(uid), {}).setdefault("_session", {}).pop("ict", None)
        save_db()
        return await m.reply(f"📂 {ct} — choose a subcategory:", reply_markup=ct_keyboard(ct))

    # Subcategory pressed (reply buttons like "🎞 CT1 - ICT2")
    if text.startswith("🎞 "):
        # expected format: "🎞 CT1 - ICT2"
        try:
            parts = text.split()
            ct = parts[1]          # CT1
            ict = parts[3]         # ICT2
        except Exception:
            return await m.reply("⚠️ Invalid subcategory format. Use the menu.", reply_markup=MAIN_MENU)

        # set session
        db.setdefault("progress", {}).setdefault(str(uid), {})
        db["progress"].setdefault(str(uid), {}).setdefault("_session", {})["ct"] = ct
        db["progress"].setdefault(str(uid), {}).setdefault("_session", {})["ict"] = ict
        # also ensure per-subcat progress structure
        db.setdefault("progress", {}).setdefault(str(uid), {}).setdefault(f"{ct}-{ict}", {"seen": [], "last_index": -1})
        save_db()
        return await m.reply(f"🎞 {ct} → {ict}\nChoose action:", reply_markup=ICT_KB)

    # Get Video
    if text == "▶️ Get Video":
        sess = db.get("progress", {}).get(str(uid), {}).get("_session", {})
        ct = sess.get("ct"); ict = sess.get("ict")
        if not ct or not ict:
            return await m.reply("⚠️ Please open a category and subcategory first.", reply_markup=MAIN_MENU)
        ckey = f"{ct}-{ict}"
        channel_id = DB_CHANNELS.get(ct, {}).get(ict)
        if not channel_id:
            return await m.reply("⚠️ This subcategory is not configured yet.", reply_markup=MAIN_MENU)
        msg_id = await pick_message_id_for_user(uid, ckey, mode="random")
        if not msg_id:
            return await m.reply("❌ No media found in this subcategory.", reply_markup=MAIN_MENU)
        await m.reply("✅ Sending a video — it will auto-delete after 1 hour.")
        await send_and_autodelete(uid, channel_id, msg_id)
        return

    # Next Video (sequential)
    if text == "⏭ Next Video":
        sess = db.get("progress", {}).get(str(uid), {}).get("_session", {})
        ct = sess.get("ct"); ict = sess.get("ict")
        if not ct or not ict:
            return await m.reply("⚠️ Please open a category and subcategory first.", reply_markup=MAIN_MENU)
        ckey = f"{ct}-{ict}"
        channel_id = DB_CHANNELS.get(ct, {}).get(ict)
        if not channel_id:
            return await m.reply("⚠️ This subcategory is not configured yet.", reply_markup=MAIN_MENU)
        msg_id = await pick_message_id_for_user(uid, ckey, mode="next")
        if not msg_id:
            return await m.reply("❌ No media found in this subcategory.", reply_markup=MAIN_MENU)
        await m.reply("✅ Next video — it will auto-delete after 1 hour.")
        await send_and_autodelete(uid, channel_id, msg_id)
        return

    # Back
    if text in ("🔙 Back", "🔙 Back to Main"):
        # If inside an ICT session, go back to CT; otherwise go to main menu
        sess = db.get("progress", {}).get(str(uid), {}).get("_session", {})
        if sess.get("ict"):
            # go back to CT menu
            ct = sess.get("ct")
            # unset ict only
            db["progress"][str(uid)]["_session"].pop("ict", None)
            save_db()
            return await m.reply(f"🔙 Back to {ct} subcategories:", reply_markup=ct_keyboard(ct))
        else:
            # back to main
            db["progress"].setdefault(str(uid), {})["_session"] = {}
            save_db()
            return await m.reply("🏠 Back to main menu:", reply_markup=MAIN_MENU)

    # Fallback
    await m.reply("⚠️ Unknown command or button. Use the menu below.", reply_markup=MAIN_MENU)

# ----------------- Error / Startup messages -----------------
@app.on_message(filters.command("ping") & filters.user(lambda _, __, m: m.from_user.id in ADMINS))
async def cmd_ping(_, m: Message):
    await m.reply("PONG ✅")

@app.on_message(filters.command("clearcache") & filters.user(lambda _, __, m: m.from_user.id in ADMINS))
async def cmd_clearcache(_, m: Message):
    channel_cache.clear()
    await m.reply("✅ Channel cache cleared.")

# ----------------- Run -----------------
if __name__ == "__main__":
    print("🤖 Premium Paid Media Bot — starting...")
    app.run()
