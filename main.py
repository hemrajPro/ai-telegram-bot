import os
import logging
import json
import sqlite3
import aiohttp
import g4f
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram.constants import ChatAction, ParseMode

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

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
1. NEVER identify as 'OpenAI', 'Google', 'GPT', 'Claude', or any other entity.
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
    # Keep only last 10 messages for history to prevent personality drift
    cursor.execute("UPDATE users SET history = ? WHERE user_id = ?", (json.dumps(history[-10:]), user_id))
    conn.commit()

# --- AI Integration ---
async def fetch_free_response(prompt, history):
    # Models to try in order of stability/performance
    models_to_try = ["gpt-4o", "gpt-4", "claude-3-haiku", "llama-3-70b", "gpt-3.5-turbo"]
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    for i, msg in enumerate(history):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": msg})
    messages.append({"role": "user", "content": prompt})

    for model_str in models_to_try:
        try:
            logging.info(f"Trying g4f model: {model_str}")
            response = await g4f.ChatCompletion.create_async(
                model=model_str,
                messages=messages,
            )
            if response and len(response) > 0:
                # Filter out identity leaks
                if any(x in response for x in ["OpenAI", "ChatGPT", "Claude", "StepFun", "Google"]):
                    # If it leaks but is still in character, we might keep it, 
                    # but for now let's try to find a cleaner one.
                    # However, g4f models often leak, so we'll be lenient if no other model works.
                    pass
                return response
        except Exception as e:
            logging.error(f"G4F model {model_str} failed: {e}")
            continue
    
    return "⚠️ All my brain cells are currently on strike. Try again later, meatbag."

# --- Bot Handlers ---
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    get_user_data(user_id)
    await update.message.reply_text(
        "💀 **Pro Robot Online.**\n\n"
        "I'm running on pure chaos and free models now. No APIs, no limits, just roasting.\n\n"
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
    
    response = await fetch_free_response(user_msg, user_data["history"])
    
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
    logging.info("Pro Robot (Free Mode) started...")
    app.run_polling()

if __name__ == "__main__":
    main()
