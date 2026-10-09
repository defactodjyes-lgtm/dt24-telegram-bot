import os
import asyncio
import logging
import threading
import requests

from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

app = Flask(__name__)

# Render Environment Variables
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
API_KEY = os.environ["GEMINI_API_KEY"].strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_PROMPT = (
    "You are Dt24Classes AI Tutor. "
    "Answer questions accurately and helpfully. "
    "Reply in Kannada when the user writes in Kannada. "
    "Otherwise reply in the user's language. "
    "Explain educational topics in a student-friendly way."
)


# Website health check
@app.route("/")
def home():
    return "Dt24Classes AI Bot is Running Live!", 200


# Gemini API request
def ask_gemini(history):
    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{MODEL}:generateContent"
    )

    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": history,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
        },
    }

    response = requests.post(
        url,
        headers={
            "x-goog-api-key": API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    if response.status_code != 200:
        logging.error(
            "GEMINI ERROR %s: %s",
            response.status_code,
            response.text[:1500],
        )
        return None, response.status_code

    data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        logging.error("Gemini returned no candidates: %s", data)
        return None, 200

    parts = candidates[0].get("content", {}).get("parts", [])
    answer = "".join(
        part.get("text", "")
        for part in parts
        if "text" in part
    )

    return answer or None, 200


# Start command
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "ನಮಸ್ಕಾರ! Dt24Classes AI Tutor ಗೆ ಸ್ವಾಗತ! 🎓\n\n"
        "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಕನ್ನಡ ಅಥವಾ English ನಲ್ಲಿ ಕೇಳಿ.\n\n"
        "/reset - ಸಂಭಾಷಣೆ ಮರುಹೊಂದಿಸಲು"
    )


# Reset conversation
async def reset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop("history", None)
    await update.message.reply_text(
        "ನಿಮ್ಮ ಸಂಭಾಷಣೆಯನ್ನು ಮರುಹೊಂದಿಸಲಾಗಿದೆ. 😊"
    )


# Handle user messages
async def reply_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    question = update.message.text.strip()
    if not question:
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    history = context.user_data.setdefault("history", [])
    history.append({
        "role": "user",
        "parts": [{"text": question}],
    })

    # Keep recent conversation turns
    history = history[-10:]
    context.user_data["history"] = history

    try:
        answer, status_code = await asyncio.to_thread(
            ask_gemini, history
        )

        if status_code != 200:
            if status_code == 400:
                message = (
                    "ಪ್ರಶ್ನೆ ಅಥವಾ API request ನಲ್ಲಿ ದೋಷವಿದೆ. "
                    "Render Logs ಪರಿಶೀಲಿಸಿ."
                )
            elif status_code == 401:
                message = (
                    "API key authentication ವಿಫಲವಾಗಿದೆ. "
                    "Render Environment ನಲ್ಲಿ GEMINI_API_KEY ಪರಿಶೀಲಿಸಿ."
                )
            elif status_code == 403:
                message = (
                    "API access ನಿರಾಕರಿಸಲಾಗಿದೆ. "
                    "Google AI Studio key restrictions ಪರಿಶೀಲಿಸಿ."
                )
            elif status_code == 404:
                message = (
                    "Gemini model ಲಭ್ಯವಿಲ್ಲ. "
                    "GEMINI_MODEL ಮೌಲ್ಯ ಪರಿಶೀಲಿಸಿ."
                )
            elif status_code == 429:
                message = (
                    "Gemini API quota ಮೀರಿದೆ. "
                    "ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
                )
            else:
                message = (
                    f"Gemini API error: {status_code}. "
                    "Render Logs ಪರಿಶೀಲಿಸಿ."
                )

            await update.message.reply_text(message)
            return

        if not answer:
            await update.message.reply_text(
                "ಕ್ಷಮಿಸಿ, ಈ ಬಾರಿ ಉತ್ತರ ಸಿಗಲಿಲ್ಲ. "
                "ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ."
            )
            return

        history.append({
            "role": "model",
            "parts": [{"text": answer}],
        })
        context.user_data["history"] = history[-10:]

        # Telegram message length limit
        for i in range(0, len(answer), 4000):
            await update.message.reply_text(
                answer[i:i + 4000]
            )

    except requests.exceptions.Timeout:
        logging.exception("Gemini request timed out")
        await update.message.reply_text(
            "AI ಉತ್ತರಿಸಲು ಹೆಚ್ಚು ಸಮಯ ತೆಗೆದುಕೊಳ್ಳುತ್ತಿದೆ. "
            "ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
        )

    except Exception:
        logging.exception("BOT ERROR")
        await update.message.reply_text(
            "ಕ್ಷಮಿಸಿ, ತಾಂತ್ರಿಕ ತೊಂದರೆ ಉಂಟಾಗಿದೆ. "
            "Render Logs ಪರಿಶೀಲಿಸಿ."
        )


# Run Telegram bot
async def run_bot():
    bot = ApplicationBuilder().token(BOT_TOKEN).build()

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("reset", reset))
    bot.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            reply_question,
        )
    )

    await bot.initialize()
    await bot.start()
    await bot.updater.start_polling()

    logging.info("Telegram bot started successfully")

    try:
        await asyncio.Event().wait()
    finally:
        await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()


def start_bot():
    asyncio.run(run_bot())


if __name__ == "__main__":
    threading.Thread(
        target=start_bot,
        daemon=True,
    ).start()

    port = int(os.environ.get("PORT", "10000"))
    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )
