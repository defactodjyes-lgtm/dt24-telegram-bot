import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Keep Render Web Service Port Alive
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

# ಅಧಿಕೃತ Google Generative AI ಸಂರಚನೆ (ಇದು AQ... ಮತ್ತು AIzaSy... ಎರಡನ್ನೂ ಬೆಂಬಲಿಸುತ್ತದೆ)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY.strip())

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction="You are a helpful educational tutor for Dt24Classes. Answer student questions accurately in the requested language (Kannada or English)."
)

async def reply_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = model.generate_content(user_text)
        if response and response.text:
            await update.message.reply_text(response.text)
        else:
            await update.message.reply_text("ಉತ್ತರ ನೀಡಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಇನ್ನೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ.")
    except Exception as e:
        await update.message.reply_text(f"ದೋಷ: {str(e)}")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        print("Error: TELEGRAM_BOT_TOKEN or GEMINI_API_KEY is not set!")
    else:
        threading.Thread(target=run_web_server, daemon=True).start()
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN.strip()).build()
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), reply_question))
        print("Dt24Classes AI ಬಾಟ್ ಲೈವ್ ಆಗಿದೆ...")
        app.run_polling()
