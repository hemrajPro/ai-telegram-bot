import os
import logging
import json
import sqlite3
import aiohttp
import g4f
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from telegram.constants import ChatAction, ParseMode

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Database Setup ---
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        selected_model TEXT DEFAULT 'gemini',
        history TEXT DEFAULT '[]'
    )
""")
conn.commit()

# --- Helper Functions ---
def get_user_data(user_id):
    cursor.execute("SELECT selected_model, history FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        try:
            history = json.loads(row[1])
        except json.JSONDecodeError:
            history = []
        return {"model": row[0], "history": history}
    else:
        # Default data for new users
        cursor.execute("INSERT INTO users (user_id, selected_model, history) VALUES (?, ?, ?)", (user_id, 'gemini', '[]'))
        conn.commit()
        return {"model": 'gemini', "history": []}

def save_user_data(user_id, model, history):
    # Keep only last 20 messages for history
    cursor.execute("UPDATE users SET selected_model = ?, history = ? WHERE user_id = ?", (model, json.dumps(history[-20:]), user_id))
    conn.commit()

# --- AI Integration ---
async def fetch_gemini_response(prompt, history):
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API Key is not configured! Please set GEMINI_API_KEY environment variable."
    
    dialogue = []
    for i, msg in enumerate(history):
        role = "user" if i % 2 == 0 else "model"
        dialogue.append({"role": role, "parts": [{"text": msg}]})
    
    dialogue.append({"role": "user", "parts": [{"text": prompt}]})
    
    data = {"contents": dialogue}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=data, timeout=30) as response:
                if response.status == 200:
                    res_json = await response.json()
                    try:
                        return res_json["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError):
                        return "⚠️ Error: Received unexpected response format from Gemini."
                return f"⚠️ Gemini Error: {response.status} - {await response.text()}"
    except Exception as e:
        return f"⚠️ Connection Error: {str(e)}"

async def fetch_g4f_response(prompt, history, model_name):
    try:
        # Map simple names to g4f models
        model_map = {
            "gpt-4": g4f.models.gpt_4,
            "claude": g4f.models.claude_3_haiku,
            "llama": g4f.models.llama_3_70b
        }
        target_model = model_map.get(model_name, g4f.models.gpt_35_turbo)
        
        messages = []
        for i, msg in enumerate(history):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({"role": role, "content": msg})
        
        messages.append({"role": "user", "content": prompt})
        
        response = await g4f.ChatCompletion.create_async(
            model=target_model,
            messages=messages,
        )
        return response
    except Exception as e:
        return f"⚠️ G4F Error: {str(e)}"

# --- Bot Handlers ---
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    get_user_data(user_id) # Ensure user exists in DB
    await update.message.reply_text(
        "👋 **Welcome to the Ultimate AI Bot!**\n\n"
        "I can use **Google Gemini** (Stable) or **GPT-4/Claude** (via gpt4free).\n\n"
        "Use /model to switch your AI engine.\n"
        "Just send me a message to start chatting!",
        parse_mode=ParseMode.MARKDOWN
    )

async def model_command(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("💎 Google Gemini (Stable)", callback_query_data='set_gemini')],
        [InlineKeyboardButton("🚀 GPT-4 (Free)", callback_query_data='set_gpt-4')],
        [InlineKeyboardButton("🎭 Claude (Free)", callback_query_data='set_claude')],
        [InlineKeyboardButton("🦙 Llama 3 (Free)", callback_query_data='set_llama')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose your AI Model:", reply_markup=reply_markup)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    new_model = query.data.replace('set_', '')
    
    user_data = get_user_data(user_id)
    save_user_data(user_id, new_model, user_data["history"])
    
    await query.edit_message_text(f"✅ Model switched to: **{new_model.upper()}**", parse_mode=ParseMode.MARKDOWN)

async def handle_message(update: Update, context: CallbackContext):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_msg = update.message.text
    user_data = get_user_data(user_id)
    
    # Send "typing..." action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    if user_data["model"] == 'gemini':
        response = await fetch_gemini_response(user_msg, user_data["history"])
    else:
        response = await fetch_g4f_response(user_msg, user_data["history"], user_data["model"])
    
    # Update History only if response is not an error
    if not response.startswith("⚠️"):
        user_data["history"].append(user_msg)
        user_data["history"].append(response)
        save_user_data(user_id, user_data["model"], user_data["history"])
    
    try:
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        # Fallback if Markdown parsing fails
        await update.message.reply_text(response)

# --- Main ---
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logging.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
