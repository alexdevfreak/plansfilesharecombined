import os
import json
import asyncio
import random
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID", 12345))
API_HASH = os.getenv("API_HASH", "abc123")
BOT_TOKEN = os.getenv("BOT_TOKEN", "token_here")
ADMIN_ID = int(os.getenv("ADMIN_ID", 123456789))

DB_FILE = "db.json"
AUTO_DELETE_SECONDS = 3600  # 1 hour

# Database channels (replace with your real ones)
DB_CHANNELS = {
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

# Premium Plans
PLANS = {
    "1w": (7, "1 Week – ₹99"),
    "1m": (30, "1 Month – ₹499"),
    "3m": (90, "3 Months – ₹1499"),
    "life": (None, "Lifetime – ₹1999"),
}

# ============== INIT BOT ==============
app = Client("premium_media_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ============== DB HANDLING ==============
def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({"users": {}, "progress": {}}, f)
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ============== KEYBOARDS ==============
def plans_keyboard():
    kb = [
        [InlineKeyboardButton(f"🔑 {PLANS[k][1]}", callback_data=f"plan_{k}")] for k in PLANS
    ]
    return InlineKeyboardMarkup(kb)

def categories_keyboard():
    kb = [
        [InlineKeyboardButton("📂 CT1", callback_data="CT1"), InlineKeyboardButton("📂 CT2", callback_data="CT2")],
        [InlineKeyboardButton("📂 CT3", callback_data="CT3"), InlineKeyboardButton("📂 CT4", callback_data="CT4")],
    ]
    return InlineKeyboardMarkup(kb)

def subcategories_keyboard(ct):
    kb = [
        [InlineKeyboardButton("🎭 ICT1", callback_data=f"{ct}-ICT1"), InlineKeyboardButton("🎶 ICT2", callback_data=f"{ct}-ICT2")],
        [InlineKeyboardButton("🎥 ICT3", callback_data=f"{ct}-ICT3")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(kb)

def video_keyboard(subcat):
    kb = [
        [InlineKeyboardButton("▶️ Get Video", callback_data=f"get_{subcat}"), InlineKeyboardButton("⏭ Next Video", callback_data=f"next_{subcat}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"back_{subcat.split('-')[0]}")],
    ]
    return InlineKeyboardMarkup(kb)

# ============== HELPERS ==============
channel_cache = {}

async def load_channel_messages(client, channel_id):
    msgs = []
    async for msg in client.get_chat_history(channel_id, limit=2000):
        if msg.video or msg.document:
            msgs.append(msg.id)
    msgs.sort()
    return msgs

async def get_video(client, user_id, subcat, next_video=False):
    db = load_db()
    if subcat not in DB_CHANNELS:
        return None

    # Load cache if empty
    if subcat not in channel_cache:
        channel_cache[subcat] = await load_channel_messages(client, DB_CHANNELS[subcat])

    vids = channel_cache[subcat]
    if not vids:
        return None

    # Track progress
    if str(user_id) not in db["progress"]:
        db["progress"][str(user_id)] = {}
    if subcat not in db["progress"][str(user_id)]:
        db["progress"][str(user_id)][subcat] = 0

    if next_video:
        db["progress"][str(user_id)][subcat] += 1
    idx = db["progress"][str(user_id)][subcat]

    if idx >= len(vids):
        db["progress"][str(user_id)][subcat] = 0
        idx = 0

    save_db(db)
    return DB_CHANNELS[subcat], vids[idx]

async def send_and_autodelete(client, chat_id, from_chat_id, msg_id):
    sent = await client.copy_message(chat_id, from_chat_id, msg_id)
    await asyncio.sleep(AUTO_DELETE_SECONDS)
    try:
        await client.delete_messages(chat_id, sent.id)
    except:
        pass

# ============== COMMANDS ==============
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    db = load_db()
    user = db["users"].get(str(message.from_user.id))

    if not user or (user["expiry"] and datetime.utcnow() > datetime.fromisoformat(user["expiry"])):
        await message.reply_text("""
👋 Welcome to **Premium Media Bot**

🔒 This bot is premium only. Please choose a plan:
""", reply_markup=plans_keyboard())
    else:
        await message.reply_text("""
✅ You are Premium!

Choose a category:
""", reply_markup=categories_keyboard())

# ============== CALLBACKS ==============
@app.on_callback_query()
async def callbacks(client, cq):
    data = cq.data

    if data.startswith("plan_"):
        plan_key = data.split("_")[1]
        await cq.message.reply_text(
            f"You chose **{PLANS[plan_key][1]}**.\n\n💳 Please pay and send screenshot."
        )

    elif data in ["CT1", "CT2", "CT3", "CT4"]:
        await cq.message.reply_text(
            f"📂 {data} → Choose a subcategory:",
            reply_markup=subcategories_keyboard(data),
        )

    elif "-ICT" in data:
        await cq.message.reply_text(
            f"🎬 {data} Videos", reply_markup=video_keyboard(data)
        )

    elif data.startswith("get_"):
        subcat = data.split("get_")[1]
        vid = await get_video(client, cq.from_user.id, subcat)
        if vid:
            await send_and_autodelete(client, cq.message.chat.id, vid[0], vid[1])
        else:
            await cq.message.reply_text("❌ No videos found.")

    elif data.startswith("next_"):
        subcat = data.split("next_")[1]
        vid = await get_video(client, cq.from_user.id, subcat, next_video=True)
        if vid:
            await send_and_autodelete(client, cq.message.chat.id, vid[0], vid[1])
        else:
            await cq.message.reply_text("❌ No videos found.")

    elif data.startswith("back_"):
        ct = data.split("_")[1]
        await cq.message.reply_text(
            f"📂 {ct} → Choose a subcategory:",
            reply_markup=subcategories_keyboard(ct),
        )

    elif data == "back_main":
        await cq.message.reply_text("Choose a category:", reply_markup=categories_keyboard())

# ============== RUN ==============
print("Bot started ✅")
app.run()
