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

# ---------------- LOGGING ----------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger("dt24classes")

web = Flask(__name__)

# ---------------- CONFIGURATION ----------------

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
API_KEY = os.environ["GEMINI_API_KEY"].strip()

MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash",
).strip()

client = genai.Client(api_key=API_KEY)

SYSTEM_PROMPT = """
You are Dt24Classes AI Tutor.

- Answer educational questions clearly and accurately.
- Reply in Kannada when the student writes in Kannada.
- Otherwise reply in the student's language.
- Explain maths and science step by step.
- Use Google Search to verify current affairs when available.
- Never invent current facts or claim to have verified something
  when you have not.
- Use the supplied India date for questions about today's date.
"""

# ---------------- WEB HEALTH CHECK ----------------

@web.route("/")
def home():
    return "Dt24Classes AI Tutor is running!", 200


@web.route("/health")
def health():
    return {"status": "ok"}, 200


# ---------------- TELEGRAM COMMANDS ----------------

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.setdefault("thinking_level", "medium")

    await update.effective_message.reply_text(
        "ನಮಸ್ಕಾರ! Dt24Classes AI Tutor ಗೆ ಸ್ವಾಗತ.\n\n"
        "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಕನ್ನಡ ಅಥವಾ English ನಲ್ಲಿ ಕೇಳಿ.\n\n"
        "Reasoning mode:\n"
        "/mode low\n"
        "/mode medium\n"
        "/mode high\n\n"
        "/reset - ಸಂಭಾಷಣೆ ಮರುಹೊಂದಿಸಲು"
    )


async def set_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not context.args:
        level = context.user_data.get(
            "thinking_level", "medium"
        )
        await update.effective_message.reply_text(
            f"ಈಗಿನ mode: {level}\n"
            "ಬಳಸಿ: /mode low, /mode medium, /mode high"
        )
        return

    level = context.args[0].lower().strip()

    if level not in ("low", "medium", "high"):
        await update.effective_message.reply_text(
            "ಸರಿಯಾದ ಆಯ್ಕೆ: /mode low, /mode medium ಅಥವಾ /mode high"
        )
        return

    context.user_data["thinking_level"] = level

    await update.effective_message.reply_text(
        f"Reasoning mode {level.upper()} ಆಗಿದೆ."
    )


async def reset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop("history", None)

    await update.effective_message.reply_text(
        "ಸಂಭಾಷಣೆ ಮರುಹೊಂದಿಸಲಾಗಿದೆ."
    )


# ---------------- GEMINI API ----------------

async def ask_gemini(prompt, level):
    for attempt in range(3):
        try:
            logger.info(
                "Calling Gemini model=%s, attempt=%s",
                MODEL,
                attempt + 1,
            )

            response = await asyncio.to_thread(
                client.interactions.create,
                model=MODEL,
                input=prompt,
                tools=[{"type": "google_search"}],
                generation_config={
                    "thinking_level": level
                },
            )

            logger.info("Gemini response received")
            return response

        except Exception as exc:
            logger.exception(
                "Gemini API request failed: %s",
                type(exc).__name__,
            )

            error = str(exc).lower()

            temporary = (
                "503" in error
                or "unavailable" in error
                or "temporarily unavailable" in error
            )

            if temporary and attempt < 2:
                await asyncio.sleep(2 * (attempt + 1))
                continue

            raise


# ---------------- MESSAGE HANDLER ----------------

async def reply_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    logger.info(
        "DEBUG: Telegram update received; update_id=%s",
        update.update_id,
    )

    if message is None or not message.text:
        logger.info("Update contains no text message")
        return

    question = message.text.strip()

    logger.info(
        "DEBUG: Text message received; length=%s",
        len(question),
    )

    today = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%d %B %Y")

    level = context.user_data.get(
        "thinking_level", "medium"
    )

    history = context.user_data.setdefault("history", [])
    history.append(("Student", question))
    history = history[-10:]
    context.user_data["history"] = history

    conversation = "\n".join(
        f"{role}: {text}"
        for role, text in history
    )

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Today's date in India is {today}.\n"
        "For current office holders, news and other changing facts, "
        "verify using Google Search when available. "
        "If verification fails, say so honestly. "
        "Do not describe today's supplied date as a future date.\n\n"
        f"Recent conversation:\n{conversation}\n\n"
        "Tutor: Answer the latest student question."
    )

    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing",
        )

        response = await ask_gemini(prompt, level)

        answer = getattr(response, "output_text", None)

        if not answer:
            logger.error("Gemini returned no output text")
            await message.reply_text(
                "ಕ್ಷಮಿಸಿ, ಈ ಬಾರಿ ಉತ್ತರ ಲಭ್ಯವಿಲ್ಲ. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
            )
            return

        history.append(("Tutor", answer))
        context.user_data["history"] = history[-10:]

        for index in range(0, len(answer), 4000):
            await message.reply_text(answer[index:index + 4000])

        logger.info("Answer sent to Telegram successfully")

    except Exception as exc:
        error = str(exc).lower()

        logger.exception(
            "Message handling failed; exception=%s",
            type(exc).__name__,
        )

        if "429" in error or "resource_exhausted" in error:
            reply = (
                "Gemini API quota ಅಥವಾ rate limit ಸಮಸ್ಯೆ ಇದೆ. "
                "Google AI Studio Usage ಪರಿಶೀಲಿಸಿ."
            )
        elif "503" in error or "unavailable" in error:
            reply = (
                "Gemini ಸೇವೆ ತಾತ್ಕಾಲಿಕವಾಗಿ ಲಭ್ಯವಿಲ್ಲ. "
                "ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
            )
        elif "401" in error or "403" in error:
            reply = (
                "Gemini API key ಅಥವಾ permission ಸಮಸ್ಯೆ ಇದೆ. "
                "Render Environment ಪರಿಶೀಲಿಸಿ."
            )
        else:
            reply = (
                "AI ಸೇವೆಯಲ್ಲಿ ದೋಷವಿದೆ. "
                "Render Logs ಪರಿಶೀಲಿಸಿ."
            )

        try:
            await message.reply_text(reply)
        except Exception:
            logger.exception("Could not send error message to Telegram")


# ---------------- START BOT ----------------

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
    await app.updater.start_polling(drop_pending_updates=False)

    logger.info("Telegram polling started successfully")

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def start_bot():
    try:
        asyncio.run(run_bot())
    except Exception:
        logger.exception("Telegram bot stopped unexpectedly")


if __name__ == "__main__":
    bot_thread = threading.Thread(
        target=start_bot,
        daemon=True,
        name="telegram-bot",
    )
    bot_thread.start()

    port = int(os.environ.get("PORT", "10000"))

    logger.info("Starting Flask health server on port %s", port)

    web.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )
