import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# ಕೀಗಳನ್ನು ಸರ್ವರ್‌ನ ಎನ್ವಿರಾನ್‌ಮೆಂಟ್‌ನಿಂದ ಪಡೆಯುವುದು (ಸುರಕ್ಷಿತ ವಿಧಾನ)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"

async def reply_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    payload = {
        "contents": [{
            "parts": [{
                "text": (
                    f"You are an expert educational tutor for Dt24Classes. "
                    f"Provide an accurate, clear, and polite answer in the same language "
                    f"(Kannada or English) for the student's question: {user_text}"
                )
            }]
        }]
    }

    try:
        response = requests.post(GEMINI_URL, json=payload, timeout=30)
        res_data = response.json()

        if "candidates" in res_data and len(res_data["candidates"]) > 0:
            candidate = res_data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            answer = "".join([p.get("text", "") for p in parts if "text" in p and not p.get("thought", False)])
            if not answer and len(parts) > 0:
                answer = parts[0].get("text", "")

            await update.message.reply_text(answer)
        else:
            print("API Response Error:", res_data)
            await update.message.reply_text("ಕ್ಷಮಿಸಿ, ಉತ್ತರಿಸಲು ಸಾಧ್ಯವಾಗುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ಪುನಃ ಪ್ರಯತ್ನಿಸಿ.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        print("Error: API Keys not set in Environment Variables!")
    else:
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), reply_question))
        print("Dt24Classes AI ಬಾಟ್ ಯಶಸ್ವಿಯಾಗಿ ಚಾಲನೆಯಲ್ಲಿದೆ...")
        app.run_polling()
