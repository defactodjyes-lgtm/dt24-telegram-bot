
import os
import asyncio
import logging
import threading
from flask import Flask
from google import genai
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)

web = Flask(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
API_KEY = os.environ["GEMINI_API_KEY"].strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

client = genai.Client(api_key=API_KEY)

SYSTEM_PROMPT = (
    "You are Dt24Classes AI Tutor. "
    "Answer educational questions accurately. "
    "Reply in Kannada when the user writes in Kannada; "
    "otherwise reply in the user's language."
)

@web.route("/")
def home():
    return "Dt24Classes Bot is Running Live!", 200

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ನಮಸ್ಕಾರ! Dt24Classes AI Bot ಗೆ ಸ್ವಾಗತ.\n"
        "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಕನ್ನಡ ಅಥವಾ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ಕೇಳಿ.\n"
        "/reset - ಸಂಭಾಷಣೆ ಮರುಹೊಂದಿಸಲು"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("history", None)
    await update.message.reply_text("ಸಂಭಾಷಣೆ ಮರುಹೊಂದಿಸಲಾಗಿದೆ.")

async def reply_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text:
        return

    question = update.message.text.strip()

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    history = context.user_data.setdefault("history", [])
    history.append({
        "role": "user",
        "parts": [{"text": question}]
    })

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=history,
            config={"system_instruction": SYSTEM_PROMPT}
        )

        answer = response.text or "ಕ್ಷಮಿಸಿ, ಉತ್ತರ ಲಭ್ಯವಿಲ್ಲ."

        history.append({
            "role": "model",
            "parts": [{"text": answer}]
        })
        context.user_data["history"] = history[-10:]

        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i:i + 4000])

    except Exception:
        logging.exception("Gemini API error")
        await update.message.reply_text(
            "ಕ್ಷಮಿಸಿ, AI ಸೇವೆಯಲ್ಲಿ ತೊಂದರೆ ಇದೆ. "
            "ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
        )

async def run_bot():
    bot = ApplicationBuilder().token(BOT_TOKEN).build()

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("reset", reset))
    bot.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, reply_question)
    )

    await bot.initialize()
    await bot.start()
    await bot.updater.start_polling()

    try:
        await asyncio.Event().wait()
    finally:
        await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()

def start_bot():
    asyncio.run(run_bot())

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()

    port = int(os.environ.get("PORT", "10000"))
    web.run(host="0.0.0.0", port=port)
