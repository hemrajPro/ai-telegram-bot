# Ultimate AI Telegram Bot 🤖✨

A powerful, hybrid Telegram bot that merges the stability of **Google Gemini** with the variety of **gpt4free** (GPT-4, Claude, Llama). This bot allows users to switch between different AI models on the fly!

## 🌟 Features

- **Multi-Model Support**: Switch between Gemini, GPT-4, Claude, and Llama 3 using `/model`.
- **Hybrid Architecture**: Uses official Google Gemini API for stability and `g4f` for free access to other premium models.
- **Persistent Memory**: Uses SQLite to remember chat history for each user.
- **Asynchronous**: Built with `python-telegram-bot` and `aiohttp` for high performance.
- **Easy Deployment**: Ready for Heroku, Docker, or any VPS.

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.8+
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- A Google Gemini API Key (Optional but recommended, get it from [Google AI Studio](https://aistudio.google.com/))

### 2. Installation
```bash
git clone https://github.com/hemrajPro/ai-telegram-bot.git
cd ai-telegram-bot
pip install -r requirements.txt
```

### 3. Environment Variables
Set the following environment variables:
- `TELEGRAM_BOT_TOKEN`: Your bot token.
- `GEMINI_API_KEY`: Your Google Gemini API key.

### 4. Run the Bot
```bash
python main.py
```

## 🛠 Commands
- `/start`: Welcome message and instructions.
- `/model`: Open the interactive menu to switch AI models.
- `Any text`: Chat with the selected AI model.

---
Created with ❤️ by [hemrajPro](https://github.com/hemrajPro)
