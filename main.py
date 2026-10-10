import os
import asyncio
import logging
import threading

from flask import Flask
from google import genai
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
web = Flask(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
API_KEY = os.environ["GEMINI_API_KEY"].strip()
MODEL = "gemini-3.8-flash"

client = genai.Client(api_key=API_KEY)

SYSTEM_PROMPT = """
You are Dt24Classes AI Tutor.
Teach students clearly and accurately.
Reply in Kannada when the student writes in Kannada.
Otherwise reply in the student's language.
Explain answers step by step when useful.
For maths and science, show the working clearly.
If you are unsure, say so instead of inventing facts.
"""

@web.route("/")
def home():
    return "Dt24Classes AI Tutor is running!", 200


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("thinking_level", "medium")
    await update.message.reply_text(
        "ನಮಸ್ಕಾರ! Dt24Classes AI Tutor ಗೆ ಸ್ವಾಗತ.\n\n"
        "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಕನ್ನಡ ಅಥವಾ English ನಲ್ಲಿ ಕೇಳಿ.\n\n"
        "Reasoning mode ಬದಲಿಸಲು:\n"
        "/mode low\n"
        "/mode medium\n"
        "/mode high\n\n"
        "/reset - ಹಳೆಯ ಸಂಭಾಷಣೆ ಅಳಿಸಲು"
    )


async def mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        current = context.user_data.get("thinking_level", "medium")
        await update.message.reply_text(
            f"ಈಗಿನ mode: {current}\n"
            "ಬದಲಿಸಲು /mode low, /mode medium ಅಥವಾ /mode high ಬಳಸಿ."
        )
        return

    level = context.args[0].lower().strip()

    if level not in ("low", "medium", "high"):
        await update.message.reply_text(
            "ಸರಿಯಾದ ಆಯ್ಕೆ: /mode low, /mode medium ಅಥವಾ /mode high"
        )
        return

    context.user_data["thinking_level"] = level
    await update.message.reply_text(
        f"Reasoning mode ಈಗ {level.upper()} ಆಗಿದೆ."
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
    level = context.user_data.get("thinking_level", "medium")
    history = context.user_data.setdefault("history", [])

    history.append(("Student", question))

    recent_history = history[-10:]
    conversation = "\n".join(
        f"{role}: {text}" for role, text in recent_history
    )

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Conversation so far:\n{conversation}\n\n"
        "Tutor: Answer the student's latest question."
    )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    try:
        interaction = await asyncio.to_thread(
            client.interactions.create,
            model=MODEL,
            input=prompt,
            generation_config={"thinking_level": level},
        )

        answer = interaction.output_text or (
            "ಕ್ಷಮಿಸಿ, ಉತ್ತರ ಲಭ್ಯವಿಲ್ಲ."
        )

        history.append(("Tutor", answer))
        context.user_data["history"] = history[-10:]

        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i:i + 4000])

    except Exception:
        logging.exception("Gemini API error")
        await update.message.reply_text(
            "AI ಸೇವೆಯಲ್ಲಿ ತೊಂದರೆ ಇದೆ. "
            "Quota, model access ಮತ್ತು Render Logs ಪರಿಶೀಲಿಸಿ."
        )


async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("mode", mode))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            reply_question
        )
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def start_bot():
    asyncio.run(run_bot())


if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", "10000"))
    web.run(host="0.0.0.0", port=port)
