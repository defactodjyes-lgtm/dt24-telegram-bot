import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Dt24Classes Bot is Running Live!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Auth Key (AQ...) ಗೆ ಸರಿಹೊಂದುವ ಅಧಿಕೃತ v1beta ಎಂಡ್‌ಪಾಯಿಂಟ್
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

async def reply_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # ಹೊಸ AQ ಮಾದರಿಯ ಕೀಲಿಗಳನ್ನು ಸ್ವೀಕರಿಸಲು x-goog-api-key ಹೆಡರ್ ಬಳಕೆ
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    payload = {
        "contents": [{
            "parts": [{
                "text": (
                    f"You are a helpful educational tutor for Dt24Classes. "
                    f"Answer this student question accurately in the same language "
                    f"(Kannada or English): {user_text}"
                )
            }]
        }]
    }

    try:
        response = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=30)
        res_data = response.json()

        if "candidates" in res_data and len(res_data["candidates"]) > 0:
            candidate = res_data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            answer = "".join([p.get("text", "") for p in parts if "text" in p])
            if not answer and len(parts) > 0:
                answer = parts[0].get("text", "")

            await update.message.reply_text(answer)
        else:
            err_msg = res_data.get("error", {}).get("message", "API ಕಡೆಯಿಂದ ಉತ್ತರ ಬರಲಿಲ್ಲ.")
            await update.message.reply_text(f"ತೊಂದರೆ: {err_msg}")
            
    except Exception as e:
        await update.message.reply_text(f"ಸರ್ವರ್ ದೋಷ: {str(e)}")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        print("Error: Keys not set!")
    else:
        threading.Thread(target=run_web_server, daemon=True).start()
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), reply_question))
        print("Dt24Classes AI ಬಾಟ್ ಯಶಸ್ವಿಯಾಗಿ ಚಾಲನೆಯಲ್ಲಿದೆ...")
        app.run_polling()
