# bot.py
"""
✨ Premium Media Bot — Purchase-First Flow (Single File)

Flow:
1) /start -> Plans menu (non-premium users see ONLY plans & payment flow)
2) User selects plan -> sees QR/UPI + "Payment Done" button
3) User sends screenshot -> forwarded to admin -> admin Approve/Reject
4) On approval -> user becomes Premium -> sees Category menu
5) CTx -> ICTx -> [Get Video | Next Video | Go Back]
6) Media copied from private DB channels, auto-deletes after 1 hour

Storage: db.json (users, premium, states, progress)
Libs: pyrogram, tgcrypto
"""

import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List

from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)

# -------------------- CONFIG (EDIT) --------------------
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))
UPI_ID = os.environ.get("UPI_ID", "yourupi@upi")  # displayed to users

# Map "CTx-ICTy" -> private channel id (int). Fill your real channel IDs.
DB_CHANNELS: Dict[str, int] = {
    "CT1-ICT1": -1001111111111,
    "CT1-ICT2": -1002222222222,
    "CT1-ICT3": -1003333333333,
    "CT2-ICT1": -1004444444444,
    "CT2-ICT2": -1005555555555,
    "CT2-ICT3": -1006666666666,
    "CT3-ICT1": -1007777777777,
    "CT3-ICT2": -1008888888888,
    "CT3-ICT3": -1009999999999,
    "CT4-ICT1": -1001010101010,
    "CT4-ICT2": -1002020202020,
    "CT4-ICT3": -1003030303030,
}

# Plans config
PLAN_CONFIG: Dict[str, Dict[str, Any]] = {
    "1w":  {"label": "1 Week",   "price":  99,  "qr": "https://example.com/qr_1w.jpg"},
    "1m":  {"label": "1 Month",  "price": 199,  "qr": "https://example.com/qr_1m.jpg"},
    "3m":  {"label": "3 Months", "price": 499,  "qr": "https://example.com/qr_3m.jpg"},
    "life":{"label": "Lifetime", "price":1499,  "qr": "https://example.com/qr_life.jpg"},
}

DB_FILE = "db.json"
AUTO_DELETE_SECONDS = 3600  # 1 hour

# -------------------- APP --------------------
app = Client("premium_media_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# in-memory
channel_cache: Dict[str, List[int]] = {}   # channel_id str -> [message_ids]
DEFAULT_DB = {"premium": {}, "user_progress": {}, "users": [], "states": {}}

# -------------------- DB helpers --------------------
def load_db() -> Dict[str, Any]:
    if not os.path.exists(DB_FILE):
        save_db(DEFAULT_DB)
        return json.loads(json.dumps(DEFAULT_DB))
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(DEFAULT_DB))

def save_db(d: Dict[str, Any]):
    with open(DB_FILE, "w") as f:
        json.dump(d, f, indent=2, default=str)

db = load_db()

# -------------------- Premium helpers --------------------
def is_premium(user_id: int) -> bool:
    val = db.get("premium", {}).get(str(user_id))
    if not val:
        return False
    if val == "life":
        return True
    try:
        return datetime.fromisoformat(val) > datetime.now()
    except Exception:
        return False

def set_premium(user_id: int, duration_key: str):
    key = str(user_id)
    if duration_key == "life":
        db.setdefault("premium", {})[key] = "life"
    else:
        days = {"1w": 7, "1m": 30, "3m": 90}.get(duration_key, 30)
        db.setdefault("premium", {})[key] = (datetime.now() + timedelta(days=days)).isoformat()
    save_db(db)

def remove_premium(user_id: int):
    db.setdefault("premium", {}).pop(str(user_id), None)
    save_db(db)

# -------------------- UI Markups --------------------
def plans_entry_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("💎 View Plans / Buy", callback_data="choose_plan")]])

def plan_options_markup():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗓 1 Week – ₹99", callback_data="plan_1w")],
            [InlineKeyboardButton("📅 1 Month – ₹199", callback_data="plan_1m")],
            [InlineKeyboardButton("📆 3 Months – ₹499", callback_data="plan_3m")],
            [InlineKeyboardButton("👑 Lifetime – ₹1499", callback_data="plan_life")],
        ]
    )

def categories_markup():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Ⅰ CT1", callback_data="cat_CT1"),
             InlineKeyboardButton("Ⅱ CT2", callback_data="cat_CT2")],
            [InlineKeyboardButton("Ⅲ CT3", callback_data="cat_CT3"),
             InlineKeyboardButton("Ⅳ CT4", callback_data="cat_CT4")],
            [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        ]
    )

def ict_markup(cat_key: str):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Ⅰ ICT1", callback_data=f"sub_{cat_key}_ICT1"),
             InlineKeyboardButton("Ⅱ ICT2", callback_data=f"sub_{cat_key}_ICT2")],
            [InlineKeyboardButton("Ⅲ ICT3", callback_data=f"sub_{cat_key}_ICT3")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
        ]
    )

def media_options_markup(cat_key: str, ict_key: str):
    key = f"{cat_key}-{ict_key}"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶ Get Video",  callback_data=f"get_{key}"),
             InlineKeyboardButton("⏭ Next Video", callback_data=f"next_{key}")],
            [InlineKeyboardButton("🔙 Go Back", callback_data=f"back_{cat_key}")],
        ]
    )

# -------------------- Guards --------------------
async def require_premium_or_plans(cb: CallbackQuery) -> bool:
    """Gate all content actions. If not premium, push plans and stop."""
    if is_premium(cb.from_user.id):
        return True
    await cb.answer("Premium required.", show_alert=True)
    await cb.message.reply_text(
        "🔒 *Premium Only*\n\nPlease purchase a plan to access media.",
        reply_markup=plans_entry_markup()
    )
    return False

# -------------------- /start --------------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(_, m: Message):
    user_id = m.from_user.id
    if user_id not in db.get("users", []):
        db.setdefault("users", []).append(user_id)
        save_db(db)

    if is_premium(user_id):
        await m.reply_text(
            "🎉 *Welcome back, Premium user!*\n\nChoose a category:",
            reply_markup=categories_markup()
        )
        return

    text = (
        "✨ *WELCOME TO VIP MEDIA BOT* ✨\n\n"
        "💎 *AVAILABLE PLANS* 💎\n\n"
        "🗓  1 Week – ₹99\n"
        "📅  1 Month – ₹199\n"
        "📆  3 Months – ₹499\n"
        "👑  Lifetime – ₹1499\n\n"
        "⚡ *Features:*\n"
        "• Premium-only Access\n"
        "• Unlimited Media\n"
        "• Auto-Delete in 1h\n\n"
        "👉 Tap below to buy a plan."
    )
    await m.reply_text(text, reply_markup=plans_entry_markup())

# -------------------- Plans flow --------------------
@app.on_callback_query(filters.regex(r"^choose_plan$"))
async def choose_plan_cb(_, cb: CallbackQuery):
    await cb.answer()
    await cb.message.reply_text("💠 *Select your plan:*", reply_markup=plan_options_markup())

@app.on_callback_query(filters.regex(r"^plan_(1w|1m|3m|life)$"))
async def plan_selected_cb(_, cb: CallbackQuery):
    user_id = cb.from_user.id
    plan_key = cb.data.split("_")[1]
    plan = PLAN_CONFIG.get(plan_key)
    if not plan:
        return await cb.answer("Invalid plan.", show_alert=True)

    db.setdefault("states", {})[str(user_id)] = {"action": "qr_sent", "plan": plan_key}
    save_db(db)
    await cb.answer()

    caption = (
        f"💳 *Payment Details*\n\n"
        f"Plan: *{plan['label']}* — ₹{plan['price']}\n"
        f"UPI: `{UPI_ID}`\n\n"
        f"📌 After payment, *send a screenshot here* and press the button."
    )
    try:
        await cb.message.reply_photo(
            photo=plan["qr"],
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Payment Done", callback_data="payment_done")]]),
            disable_web_page_preview=True,
        )
    except Exception:
        await cb.message.reply_text(
            caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Payment Done", callback_data="payment_done")]]),
            disable_web_page_preview=True,
        )

@app.on_callback_query(filters.regex(r"^payment_done$"))
async def payment_done_cb(_, cb: CallbackQuery):
    user_id = cb.from_user.id
    state = db.setdefault("states", {}).get(str(user_id))
    if not state or state.get("action") != "qr_sent":
        return await cb.answer("No payment in progress.", show_alert=True)
    db["states"][str(user_id)]["action"] = "awaiting_screenshot"
    save_db(db)
    await cb.answer()
    await cb.message.reply_text("📸 Please *send your payment screenshot* here. Admin will verify it.")

# -------------------- Screenshot -> Admin verify --------------------
@app.on_message(filters.photo & filters.private)
async def screenshot_handler(_, m: Message):
    user_id = m.from_user.id
    state = db.setdefault("states", {}).get(str(user_id))
    if not state or state.get("action") != "awaiting_screenshot":
        return  # ignore random photos

    if m.forward_date:
        return await m.reply_text("⚠ Please send the *original* screenshot (not forwarded).")

    plan_key = state.get("plan", "1m")
    db["states"][str(user_id)]["action"] = "screenshot_sent"
    save_db(db)

    caption = (
        "🧾 *PAYMENT SCREENSHOT*\n\n"
        f"👤 Name: {m.from_user.first_name or 'N/A'}\n"
        f"🔗 Username: @{m.from_user.username or 'N/A'}\n"
        f"🆔 User ID: {user_id}\n"
        f"🔒 Plan: {PLAN_CONFIG.get(plan_key, {}).get('label', plan_key)}"
    )
    buttons = [
        [InlineKeyboardButton("✅ Approve 1w",   callback_data=f"approve_1w_{user_id}"),
         InlineKeyboardButton("✅ Approve 1m",   callback_data=f"approve_1m_{user_id}")],
        [InlineKeyboardButton("✅ Approve 3m",   callback_data=f"approve_3m_{user_id}"),
         InlineKeyboardButton("✅ Approve Life", callback_data=f"approve_life_{user_id}")],
        [InlineKeyboardButton("❌ Reject",       callback_data=f"reject_{user_id}")],
    ]

    # Send photo to admin
    try:
        await app.send_photo(ADMIN_ID, photo=m.photo.file_id, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        # Fallback: forward
        try:
            await m.forward(ADMIN_ID)
            await app.send_message(ADMIN_ID, caption, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass

    await m.reply_text("✅ Screenshot received. *Admin will verify and activate Premium soon.*")

# -------------------- Admin callbacks --------------------
@app.on_callback_query(filters.regex(r"^approve_(1w|1m|3m|life)_(\d+)$"))
async def admin_approve_cb(_, cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("Not authorized.", show_alert=True)

    _, duration, uid = cb.data.split("_")
    user_id = int(uid)
    set_premium(user_id, duration)

    try:
        val = db["premium"][str(user_id)]
        if val == "life":
            text = "🎉 Your *Lifetime Premium* has been activated!"
        else:
            expiry = val.split("T")[0]
            text = f"🎉 Your *Premium* has been activated.\n🗓 Valid till: *{expiry}*"
        await app.send_message(user_id, text)
    except Exception:
        pass

    await cb.answer("Approved.")
    try:
        await cb.message.edit_reply_markup(None)
    except Exception:
        pass

@app.on_callback_query(filters.regex(r"^reject_(\d+)$"))
async def admin_reject_cb(_, cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("Not authorized.", show_alert=True)
    user_id = int(cb.data.split("_")[1])
    try:
        await app.send_message(user_id, "❌ Your payment *could not be verified*. Please contact support.")
    except Exception:
        pass
    await cb.answer("Rejected.")
    try:
        await cb.message.edit_reply_markup(None)
    except Exception:
        pass

# -------------------- Admin CLI --------------------
@app.on_message(filters.command("authorize") & filters.user(ADMIN_ID))
async def cmd_authorize(_, m: Message):
    try:
        _, uid, duration = m.text.split()
        user_id = int(uid)
    except Exception:
        return await m.reply_text("Usage: /authorize <user_id> <1w|1m|3m|life>")

    if duration not in ("1w", "1m", "3m", "life"):
        return await m.reply_text("Invalid duration. Use: 1w | 1m | 3m | life")

    set_premium(user_id, duration)
    await m.reply_text(f"✅ Authorized {user_id} for {duration}")
    try:
        await app.send_message(user_id, "🎉 Your Premium has been activated by Admin.")
    except Exception:
        pass

@app.on_message(filters.command("unauthorize") & filters.user(ADMIN_ID))
async def cmd_unauthorize(_, m: Message):
    try:
        _, uid = m.text.split()
        user_id = int(uid)
    except Exception:
        return await m.reply_text("Usage: /unauthorize <user_id>")

    remove_premium(user_id)
    await m.reply_text(f"✅ Removed premium for {user_id}")
    try:
        await app.send_message(user_id, "⚠ Your premium access has been removed by Admin.")
    except Exception:
        pass

@app.on_message(filters.command("authorized") & filters.user(ADMIN_ID))
async def cmd_authorized(_, m: Message):
    prem = db.get("premium", {})
    if not prem:
        return await m.reply_text("No authorized users.")
    lines = ["📋 *Authorized Users:*"]
    for uid, val in prem.items():
        if val == "life":
            lines.append(f"• `{uid}` — Lifetime")
        else:
            lines.append(f"• `{uid}` — until {val.split('T')[0]}")
    await m.reply_text("\n".join(lines), disable_web_page_preview=True)

@app.on_message(filters.command("users") & filters.user(ADMIN_ID))
async def users_cmd(_, m: Message):
    total = len(db.get("users", []))
    premium_count = len(db.get("premium", {}))
    await m.reply_text(f"📊 Users: {total}\n💎 Premium: {premium_count}")

# -------------------- Profile & Menus (Premium-only) --------------------
@app.on_callback_query(filters.regex(r"^profile$"))
async def profile_cb(_, cb: CallbackQuery):
    if not await require_premium_or_plans(cb):
        return
    user_id = cb.from_user.id
    val = db.get("premium", {}).get(str(user_id))
    expiry_text = "Lifetime" if val == "life" else val.split("T")[0]
    text = f"👤 *Profile*\n\n🆔 ID: `{user_id}`\n💎 Status: *Premium*\n📅 Valid Till: *{expiry_text}*"
    await cb.answer()
    await cb.message.reply_text(text, reply_markup=categories_markup())

@app.on_callback_query(filters.regex(r"^cat_CT[1-4]$"))
async def cat_cb(_, cb: CallbackQuery):
    if not await require_premium_or_plans(cb):
        return
    cat_key = cb.data.split("_")[1]  # CT1..CT4
    await cb.answer()
    await cb.message.reply_text(f"📂 *{cat_key}* selected.\nChoose subcategory:", reply_markup=ict_markup(cat_key))

@app.on_callback_query(filters.regex(r"^sub_CT[1-4]_ICT[1-3]$"))
async def sub_cb(_, cb: CallbackQuery):
    if not await require_premium_or_plans(cb):
        return
    _, cat, ict = cb.data.split("_")  # ["sub", "CTx", "ICTy"]
    await cb.answer()
    await cb.message.reply_text(f"{cat} → {ict}\nChoose action:", reply_markup=media_options_markup(cat, ict))

@app.on_callback_query(filters.regex(r"^back_CT[1-4]$"))
async def back_cat_cb(_, cb: CallbackQuery):
    if not await require_premium_or_plans(cb):
        return
    await cb.answer()
    await cb.message.reply_text("🔙 Back to subcategories:", reply_markup=ict_markup(cb.data.split("_")[1]))

@app.on_callback_query(filters.regex(r"^back_main$"))
async def back_main_cb(_, cb: CallbackQuery):
    if not await require_premium_or_plans(cb):
        return
    await cb.answer()
    await cb.message.reply_text("🏠 Main menu:", reply_markup=categories_markup())

# -------------------- Channel indexing & media sending --------------------
async def build_channel_cache(channel_id: int) -> List[int]:
    key = str(channel_id)
    if key in channel_cache and channel_cache[key]:
        return channel_cache[key]

    message_ids: List[int] = []
    try:
        async for m in app.iter_history(channel_id, limit=2000):
            if m.media:
                message_ids.append(m.id if hasattr(m, "id") else m.message_id)
    except Exception:
        pass

    message_ids.sort()  # oldest first
    channel_cache[key] = message_ids
    return message_ids

async def send_media_for_user(user_id: int, channel_key: str, mode: str = "random"):
    channel_id = DB_CHANNELS.get(channel_key)
    if not channel_id:
        return False, "This subcategory is not configured yet."

    ids = await build_channel_cache(channel_id)
    if not ids:
        return False, "No media found in the configured channel."

    user_prog = db.setdefault("user_progress", {}).setdefault(str(user_id), {})
    prog = user_prog.setdefault(channel_key, {"seen": []})
    seen = set(prog.get("seen", []))

    available = [mid for mid in ids if mid not in seen]
    if not available:
        return False, "You have watched all videos in this subcategory."

    chosen = available[0] if mode == "next" else random.choice(available)

    try:
        sent = await app.copy_message(user_id, channel_id, chosen)
    except Exception as e:
        return False, f"Failed to send media: {e}"

    prog.setdefault("seen", []).append(chosen)
    save_db(db)

    asyncio.create_task(schedule_delete(user_id, sent.id if hasattr(sent, "id") else sent.message_id, AUTO_DELETE_SECONDS))
    return True, "Sent"

async def schedule_delete(chat_id: int, message_id: int, seconds: int):
    await asyncio.sleep(seconds)
    try:
        await app.delete_messages(chat_id, message_id)
    except Exception:
        pass

# -------------------- Get / Next (Premium-only) --------------------
@app.on_callback_query(filters.regex(r"^(get|next)_CT[1-4]-ICT[1-3]$"))
async def get_next_cb(_, cb: CallbackQuery):
    if not await require_premium_or_plans(cb):
        return
    mode = cb.data.split("_")[0]  # get | next
    channel_key = cb.data.split("_")[1]  # CTx-ICTy
    await cb.answer()
    ok, msg = await send_media_for_user(cb.from_user.id, channel_key, mode=("random" if mode == "get" else "next"))
    if not ok:
        await cb.message.reply_text(f"⚠ {msg}")
    else:
        await cb.message.reply_text("✅ Enjoy — this video will auto-delete after 1 hour.")

# -------------------- /profile (Premium-only) --------------------
@app.on_message(filters.command("profile") & filters.private)
async def profile_cmd(_, m: Message):
    user_id = m.from_user.id
    if not is_premium(user_id):
        return await m.reply_text(
            "🔒 *Premium Only*\n\nPurchase a plan to access content.",
            reply_markup=plans_entry_markup()
        )
    val = db.get("premium", {}).get(str(user_id))
    expiry_text = "Lifetime" if val == "life" else val.split("T")[0]
    await m.reply_text(
        f"👤 *Profile*\n\n🆔 ID: `{user_id}`\n💎 Status: *Premium*\n📅 Valid Till: *{expiry_text}*",
        reply_markup=categories_markup()
    )

# -------------------- Run --------------------
if __name__ == "__main__":
    print("🤖 Premium Media Bot starting...")
    app.run()
