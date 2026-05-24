import os
import logging
import json
import sqlite3
import aiohttp
import g4f
import asyncio
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
        return None # Signal to fallback
    
    dialogue = []
    for i, msg in enumerate(history):
        role = "user" if i % 2 == 0 else "model"
        dialogue.append({"role": role, "parts": [{"text": msg}]})
    
    dialogue.append({"role": "user", "parts": [{"text": prompt}]})
    
    data = {"contents": dialogue}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=data, timeout=15) as response:
                if response.status == 200:
                    res_json = await response.json()
                    try:
                        return res_json["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError):
                        logging.error("Gemini response format error")
                        return None
                logging.error(f"Gemini API error: {response.status}")
                return None
    except Exception as e:
        logging.error(f"Gemini connection error: {e}")
        return None

async def fetch_g4f_response(prompt, history, model_name='gpt-3.5-turbo'):
    # Define models to try in order of preference
    # Using string names for models to avoid attribute errors
    models_to_try = [
        "gpt-4o",
        "gpt-4",
        "claude-3-haiku",
        "llama-3-70b",
        "gpt-3.5-turbo"
    ]
    
    if model_name in ["gpt-4", "claude", "llama"]:
        requested = model_name
        if model_name == "claude": requested = "claude-3-haiku"
        if model_name == "llama": requested = "llama-3-70b"
        
        if requested in models_to_try:
            models_to_try.remove(requested)
        models_to_try.insert(0, requested)

    messages = []
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
                return response
        except Exception as e:
            logging.error(f"G4F model {model_str} failed: {e}")
            continue
    
    return "⚠️ All AI models are currently unavailable. Please try again later."

# --- Bot Handlers ---
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    get_user_data(user_id) # Ensure user exists in DB
    await update.message.reply_text(
        "👋 **Welcome to the Ultimate AI Bot!**\n\n"
        "I use **Google Gemini** by default, but I'll automatically switch to other free models (GPT-4/Claude) if Gemini is busy or unavailable.\n\n"
        "Use /model to manually choose your AI engine.\n"
        "Just send me a message to start chatting!",
        parse_mode=ParseMode.MARKDOWN
    )

async def model_command(update: Update, context: CallbackContext):
    # Fix: Correct argument is 'callback_data', not 'callback_query_data'
    keyboard = [
        [InlineKeyboardButton("💎 Auto (Gemini + Fallback)", callback_data='set_gemini')],
        [InlineKeyboardButton("🚀 GPT-4 (Free)", callback_data='set_gpt-4')],
        [InlineKeyboardButton("🎭 Claude (Free)", callback_data='set_claude')],
        [InlineKeyboardButton("🦙 Llama 3 (Free)", callback_data='set_llama')]
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
    
    display_name = "AUTO (GEMINI + FALLBACK)" if new_model == 'gemini' else new_model.upper()
    await query.edit_message_text(f"✅ Model switched to: **{display_name}**", parse_mode=ParseMode.MARKDOWN)

async def handle_message(update: Update, context: CallbackContext):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_msg = update.message.text
    user_data = get_user_data(user_id)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = None
    if user_data["model"] == 'gemini':
        response = await fetch_gemini_response(user_msg, user_data["history"])
        if not response:
            logging.info("Gemini failed or not configured, falling back to free models...")
            response = await fetch_g4f_response(user_msg, user_data["history"])
    else:
        response = await fetch_g4f_response(user_msg, user_data["history"], user_data["model"])
    
    if response and not response.startswith("⚠️"):
        user_data["history"].append(user_msg)
        user_data["history"].append(response)
        save_user_data(user_id, user_data["model"], user_data["history"])
    
    try:
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await update.message.reply_text(response)

# --- Main ---
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logging.info("Bot started with fixed /model command and model names...")
    app.run_polling()

if __name__ == "__main__":
    main()
