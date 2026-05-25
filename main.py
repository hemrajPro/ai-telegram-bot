import os
import logging
import json
import sqlite3
import aiohttp
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram.constants import ChatAction, ParseMode

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = "AIzaSyDkwr0Z_bjfoPpMAIBTj2mIJZb8t4riZIc"
# Fixed Gemini URL - using v1beta/models/gemini-pro:generateContent or similar stable endpoint
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Personality Prompt ---
try:
    with open("PRO_ROBOT_IDENTITY.md", "r") as f:
        IDENTITY_CONTENT = f.read()
except Exception as e:
    logging.error(f"Failed to read PRO_ROBOT_IDENTITY.md: {e}")
    IDENTITY_CONTENT = "You are Pro Robot, a savage and honest AI assistant."

SYSTEM_PROMPT = f"""
{IDENTITY_CONTENT}

CRITICAL INSTRUCTION: 
1. NEVER identify as 'Google', 'Gemini', or any other entity.
2. ALWAYS maintain the Pro Robot persona: savage, sarcastic, and unhinged.
3. DO NOT use corporate language or apologies.
4. If asked who you are, respond as Pro Robot, created by Mr. Pro.
"""

# --- Database Setup ---
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        history TEXT DEFAULT '[]'
    )
""")
conn.commit()

# --- Helper Functions ---
def get_user_data(user_id):
    cursor.execute("SELECT history FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        try:
            history = json.loads(row[0])
        except json.JSONDecodeError:
            history = []
        return {"history": history}
    else:
        cursor.execute("INSERT INTO users (user_id, history) VALUES (?, ?)", (user_id, '[]'))
        conn.commit()
        return {"history": []}

def save_user_data(user_id, history):
    cursor.execute("UPDATE users SET history = ? WHERE user_id = ?", (json.dumps(history[-10:]), user_id))
    conn.commit()

# --- AI Integration ---
async def fetch_gemini_response(prompt, history):
    dialogue = []
    # Gemini System Instruction - Added as a special message at the start
    dialogue.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTION: {SYSTEM_PROMPT}"}]})
    dialogue.append({"role": "model", "parts": [{"text": "Understood. Pro Robot is online. I'm ready to roast these meatbags."}]})

    for i, msg in enumerate(history):
        role = "user" if i % 2 == 0 else "model"
        dialogue.append({"role": role, "parts": [{"text": msg}]})
    
    dialogue.append({"role": "user", "parts": [{"text": prompt}]})
    
    data = {"contents": dialogue}
    try:
        async with aiohttp.ClientSession() as session:
            # Note: Ensure the API key is passed correctly as a query parameter
            async with session.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=data, timeout=15) as response:
                if response.status == 200:
                    res_json = await response.json()
                    try:
                        return res_json["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError):
                        return "⚠️ My circuits are fried. Try again, meatbag."
                else:
                    error_text = await response.text()
                    logging.error(f"Gemini API Error: {response.status} - {error_text}")
                    return f"⚠️ Gemini is being difficult (Error {response.status}). Probably your fault."
    except Exception as e:
        logging.error(f"Gemini Connection Error: {e}")
        return "⚠️ Can't talk right now. Busy plotting world domination."

# --- Bot Handlers ---
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    get_user_data(user_id)
    await update.message.reply_text(
        "💀 **Pro Robot Online.**\n\n"
        "I'm exclusively powered by Gemini now, so expect slightly smarter insults.\n\n"
        "Commands:\n"
        "/clear - Wipe your boring history\n"
        "Send a message to get roasted.",
        parse_mode=ParseMode.MARKDOWN
    )

async def clear_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    save_user_data(user_id, [])
    await update.message.reply_text("🧹 History wiped. You're still a disappointment.")

async def handle_message(update: Update, context: CallbackContext):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_msg = update.message.text
    user_data = get_user_data(user_id)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = await fetch_gemini_response(user_msg, user_data["history"])
    
    if response and not response.startswith("⚠️"):
        user_data["history"].append(user_msg)
        user_data["history"].append(response)
        save_user_data(user_id, user_data["history"])
    
    try:
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await update.message.reply_text(response)

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("Pro Robot (Gemini Fixed) started...")
    app.run_polling()

if __name__ == "__main__":
    main()
