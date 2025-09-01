# config.py

# ========== BOT CONFIG ==========
API_ID = 1234567  # Your Telegram API_ID (from my.telegram.org)
API_HASH = "your_api_hash_here"  # Your Telegram API_HASH
BOT_TOKEN = "your_bot_token_here"  # Bot token from BotFather

# ========== DATABASE ==========
MONGO_DB_URI = "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "PremiumMediaBot"

# ========== ADMINS ==========
# 1 Owner (Main Controller)
OWNER_ID = 123456789  # Replace with your Telegram User ID

# Multiple Admins (Helpers)
ADMINS = [987654321, 135791113]  
# Add more IDs if needed

# Function to check permissions
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS or user_id == OWNER_ID

# ========== PAYMENT / PREMIUM ==========
PAYMENT_CHANNEL = -100123456789  # Telegram channel/group ID where users send proof
PREMIUM_PLAN_PRICE = 100  # Example: 100 INR per plan
CURRENCY = "INR"

# ========== MEDIA SOURCE CHANNELS ==========
MEDIA_DB = {
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

# ========== MISC ==========
LOG_CHANNEL = -1001515151515  # For logging bot activities
SUPPORT_GROUP = "https://t.me/YourSupportGroup"

