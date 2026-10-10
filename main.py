import os
import asyncio
import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

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

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

web = Flask(__name__)

# Render Environment Variables
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
API_KEY = os.environ["GEMINI_API_KEY"].strip()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

client = genai.Client(api_key=API_KEY)

SYSTEM_PROMPT = """
You are Dt24Classes AI Tutor.

Rules:
1. Reply in Kannada when the student writes in Kannada.
2. Otherwise reply in the student's language.
3. Teach students clearly, accurately and patiently.
4. Explain mathematics and science step by step.
5. For current affairs, current office holders, news and changing facts,
   use Google Search to verify the latest information.
6. Never present old information as current.
7. If current information cannot be verified, clearly say so.
8. Use the supplied India date when answering questions about today's date.
9. Never invent facts, dates, search results or sources.
"""


@web.route("/")
def home():
    return "Dt24Classes AI Tutor is Running!", 200


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.setdefault("thinking_level", "medium")

    await update.effective_message.reply_text(
        "ನಮಸ್ಕಾರ! Dt24Classes AI Tutor ಗೆ ಸ್ವಾಗತ.\n\n"
        "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಕನ್ನಡ ಅಥವಾ English ನಲ್ಲಿ ಕೇಳಿ.\n\n"
        "Reasoning mode:\n"
        "/mode low - ವೇಗದ ಉತ್ತರ\n"
        "/mode medium - ಸಾಮಾನ್ಯ ಬಳಕೆ\n"
        "/mode high - ಕಠಿಣ ಪ್ರಶ್ನೆಗಳು\n\n"
        "/reset - ಸಂಭಾಷಣೆ ಮರುಹೊಂದಿಸಲು"
    )


async def set_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not context.args:
        current = context.user_data.get(
            "thinking_level", "medium"
        )
        await update.effective_message.reply_text(
            f"ಈಗಿನ mode: {current}\n"
            "ಬದಲಿಸಲು /mode low, /mode medium ಅಥವಾ /mode high ಬಳಸಿ."
        )
        return

    level = context.args[0].lower().strip()

    if level not in ("low", "medium", "high"):
        await update.effective_message.reply_text(
            "ಸರಿಯಾದ command:\n"
            "/mode low\n"
            "/mode medium\n"
            "/mode high"
        )
        return

    context.user_data["thinking_level"] = level

    await update.effective_message.reply_text(
        f"Reasoning mode {level.upper()} ಆಗಿ ಬದಲಾಯಿಸಲಾಗಿದೆ."
    )


async def reset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop("history", None)

    await update.effective_message.reply_text(
        "ಸಂಭಾಷಣೆ ಮರುಹೊಂದಿಸಲಾಗಿದೆ."
    )


async def ask_gemini(prompt, level):
    """Call Gemini and retry temporary 503 errors."""
    for attempt in range(3):
        try:
            return await asyncio.to_thread(
                client.interactions.create,
                model=MODEL,
                input=prompt,
                tools=[{"type": "google_search"}],
                generation_config={
                    "thinking_level": level
                },
            )

        except Exception as exc:
            error_text = str(exc).lower()

            temporary_error = (
                "503" in error_text
                or "unavailable" in error_text
                or "temporarily unavailable" in error_text
            )

            if temporary_error and attempt < 2:
                wait_seconds = 2 * (attempt + 1)
                logger.warning(
                    "Temporary Gemini error. Retry %s/2 after %s seconds.",
                    attempt + 1,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                continue

            raise


async def reply_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message or not message.text:
        return

    question = message.text.strip()

    if not question:
        return

    # Current date in India
    today = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%Y-%m-%d")

    level = context.user_data.get(
        "thinking_level", "medium"
    )

    history = context.user_data.setdefault("history", [])

    # Save latest student question
    history.append(("Student", question))

    # Keep recent conversation only
    history = history[-10:]
    context.user_data["history"] = history

    conversation = "\n".join(
        f"{role}: {text}"
        for role, text in history
    )

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Current date in India (Asia/Kolkata): {today}\n\n"
        "Important date instructions:\n"
        "- Treat the supplied date as today's actual date in India.\n"
        "- Do not call today's date a future date.\n"
        "- For current office holders and current affairs, "
        "verify using Google Search before answering.\n"
        "- If search fails, do not pretend that verification succeeded.\n\n"
        f"Recent conversation:\n{conversation}\n\n"
        "Answer the student's latest question clearly."
    )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    try:
        response = await ask_gemini(prompt, level)

        answer = response.output_text

        if not answer:
            answer = (
                "ಕ್ಷಮಿಸಿ, ಈ ಬಾರಿ ಉತ್ತರ ಲಭ್ಯವಿಲ್ಲ. "
                "ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ."
            )

        history.append(("Tutor", answer))
        context.user_data["history"] = history[-10:]

        # Telegram message length limit
        for i in range(0, len(answer), 4000):
            await message.reply_text(answer[i:i + 4000])

    except Exception as exc:
        logger.exception("Gemini API request failed")

        error_text = str(exc).lower()

        if "429" in error_text or "resource_exhausted" in error_text:
            user_message = (
                "Gemini API quota ಮೀರಿದೆ. "
                "Google AI Studioನಲ್ಲಿ usage ಮತ್ತು quota ಪರಿಶೀಲಿಸಿ."
            )
        elif "503" in error_text or "unavailable" in error_text:
            user_message = (
                "Gemini ಸೇವೆ ತಾತ್ಕಾಲಿಕವಾಗಿ ಲಭ್ಯವಿಲ್ಲ. "
                "ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
            )
        elif "401" in error_text or "403" in error_text:
            user_message = (
                "Gemini API authentication ಅಥವಾ permission ಸಮಸ್ಯೆ ಇದೆ. "
                "Render Environmentನಲ್ಲಿ GEMINI_API_KEY ಪರಿಶೀಲಿಸಿ."
            )
        else:
            user_message = (
                "Gemini API error ಬಂದಿದೆ. "
                "ನಿಖರ ಕಾರಣಕ್ಕಾಗಿ Render Logs ಪರಿಶೀಲಿಸಿ."
            )

        await message.reply_text(user_message)


async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("mode", set_mode))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            reply_question,
        )
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    logger.info("Telegram bot started successfully.")

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def start_bot():
    asyncio.run(run_bot())


if __name__ == "__main__":
    threading.Thread(
        target=start_bot,
        daemon=True,
    ).start()

    port = int(os.environ.get("PORT", "10000"))

    web.run(
        host="0.0.0.0",
        port=port,
    )
