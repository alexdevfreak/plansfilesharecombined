import os
import json
import random
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID", "123456"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")
ADMINS = [int(x) for x in os.getenv("ADMINS", "123456789").split(",")]

# Example channel mapping (replace with your private DB channels)
DB_CHANNELS = {
    "CT1": {
        "ICT1": -1001111111111,
        "ICT2": -1002222222222,
        "ICT3": -1003333333333,
    },
    "CT2": {
        "ICT1": -1004444444444,
        "ICT2": -1005555555555,
        "ICT3": -1006666666666,
    },
    "CT3": {
        "ICT1": -1007777777777,
        "ICT2": -1008888888888,
        "ICT3": -1009999999999,
    },
    "CT4": {
        "ICT1": -1001212121212,
        "ICT2": -1001313131313,
        "ICT3": -1001414141414,
    },
}

DB_FILE = "db.json"

# =============== DATABASE HANDLER ===============
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "progress": {}}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

db = load_db()

# =============== BOT INIT ===============
app = Client("premium_media_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# =============== HELPERS ===============
def is_premium(user_id):
    user = db["users"].get(str(user_id))
    if not user:
        return False
    if user["expiry"] == "life":
        return True
    expiry = datetime.fromisoformat(user["expiry"])
    return datetime.utcnow() < expiry

# =============== REPLY KEYBOARDS ===============
main_menu = ReplyKeyboardMarkup(
    [[KeyboardButton("📂 CT1"), KeyboardButton("📂 CT2")],
     [KeyboardButton("📂 CT3"), KeyboardButton("📂 CT4")],
     [KeyboardButton("🧾 Profile")]],
    resize_keyboard=True
)

def ct_menu(ct):
    return ReplyKeyboardMarkup(
        [[KeyboardButton(f"🎞 {ct} - ICT1"), KeyboardButton(f"🎞 {ct} - ICT2"), KeyboardButton(f"🎞 {ct} - ICT3")],
         [KeyboardButton("🔙 Go Back")]],
        resize_keyboard=True
    )

def ict_menu():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🎥 Get Video")],
         [KeyboardButton("⏭ Next Video")],
         [KeyboardButton("🔙 Go Back")]],
        resize_keyboard=True
    )

# =============== COMMANDS ===============
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    user_id = str(message.from_user.id)
    if user_id not in db["users"]:
        db["users"][user_id] = {"expiry": None}
        save_db()
    await message.reply("👋 Welcome! Choose a category:", reply_markup=main_menu)

@app.on_message(filters.command("help"))
async def help_handler(client, message):
    await message.reply("ℹ️ Use the menu buttons below to explore content. If you are not authorized, contact admin.", reply_markup=main_menu)

@app.on_message(filters.command("profile"))
async def profile_handler(client, message):
    user_id = str(message.from_user.id)
    user = db["users"].get(user_id)
    if not user or not user["expiry"]:
        await message.reply("❌ You are not authorized.")
        return
    expiry = user["expiry"]
    if expiry == "life":
        await message.reply("🧾 Profile\nStatus: Premium ✅\nExpiry: Lifetime")
    else:
        await message.reply(f"🧾 Profile\nStatus: Premium ✅\nExpiry: {expiry}")

# =============== ADMIN COMMANDS ===============
@app.on_message(filters.command("authorize") & filters.user(ADMINS))
async def authorize_handler(client, message):
    try:
        _, user_id, duration = message.text.split()
        user_id = str(user_id)
        if duration == "life":
            db["users"][user_id] = {"expiry": "life"}
        else:
            num = int(duration[:-1])
            unit = duration[-1]
            now = datetime.utcnow()
            if unit == "d":
                expiry = now + timedelta(days=num)
            elif unit == "m":
                expiry = now + timedelta(days=30*num)
            elif unit == "y":
                expiry = now + timedelta(days=365*num)
            else:
                await message.reply("❌ Invalid duration format. Use d/m/y/life.")
                return
            db["users"][user_id] = {"expiry": expiry.isoformat()}
        save_db()
        await message.reply(f"✅ Authorized user {user_id} for {duration}.")
    except Exception as e:
        await message.reply("❌ Usage: /authorize <user_id> <1d|1m|1y|life>")

@app.on_message(filters.command("unauthorize") & filters.user(ADMINS))
async def unauthorize_handler(client, message):
    try:
        _, user_id = message.text.split()
        user_id = str(user_id)
        if user_id in db["users"]:
            del db["users"][user_id]
            save_db()
            await message.reply(f"❌ Unauthorized user {user_id}.")
        else:
            await message.reply("User not found.")
    except:
        await message.reply("❌ Usage: /unauthorize <user_id>")

# =============== MENU HANDLING ===============
@app.on_message(filters.text)
async def menu_handler(client, message):
    user_id = str(message.from_user.id)
    text = message.text

    # Check premium access
    if not is_premium(user_id):
        await message.reply("🚫 You are not authorized. Contact admin.")
        return

    # Main menu categories
    if text in ["📂 CT1", "📂 CT2", "📂 CT3", "📂 CT4"]:
        ct = text.split()[1]
        db["progress"][user_id] = {"ct": ct, "ict": None, "index": 0}
        save_db()
        await message.reply(f"📂 You opened {ct}", reply_markup=ct_menu(ct))
        return

    # ICT menu
    if text.startswith("🎞 "):
        ct, ict = text.split()[1], text.split()[3]
        db["progress"][user_id] = {"ct": ct, "ict": ict, "index": 0}
        save_db()
        await message.reply(f"🎞 You opened {ct}-{ict}", reply_markup=ict_menu())
        return

    # Get Video
    if text == "🎥 Get Video":
        prog = db["progress"].get(user_id)
        if not prog or not prog["ict"]:
            await message.reply("❌ Please select a category first.")
            return
        ct, ict = prog["ct"], prog["ict"]
        channel = DB_CHANNELS[ct][ict]
        async for msg in app.get_chat_history(channel, limit=100):
            if msg.video or msg.document:
                await msg.copy(user_id, caption=f"🎬 {ct}-{ict} Video")
                break
        return

    # Next Video
    if text == "⏭ Next Video":
        prog = db["progress"].get(user_id)
        if not prog or not prog["ict"]:
            await message.reply("❌ Please select a category first.")
            return
        ct, ict = prog["ct"], prog["ict"]
        channel = DB_CHANNELS[ct][ict]
        index = prog["index"] + 1
        msgs = [m async for m in app.get_chat_history(channel, limit=50)]
        vids = [m for m in msgs if m.video or m.document]
        if index >= len(vids):
            await message.reply("⚠️ No more videos.")
            return
        msg = vids[index]
        await msg.copy(user_id, caption=f"🎬 {ct}-{ict} Video {index+1}")
        prog["index"] = index
        db["progress"][user_id] = prog
        save_db()
        return

    # Go Back
    if text == "🔙 Go Back":
        prog = db["progress"].get(user_id, {})
        if prog.get("ict"):
            ct = prog["ct"]
            prog["ict"] = None
            db["progress"][user_id] = prog
            save_db()
            await message.reply(f"📂 Back to {ct}", reply_markup=ct_menu(ct))
        elif prog.get("ct"):
            db["progress"][user_id] = {"ct": None, "ict": None, "index": 0}
            save_db()
            await message.reply("🏠 Back to main menu", reply_markup=main_menu)
        else:
            await message.reply("🏠 Main menu", reply_markup=main_menu)
        return

app.run()
