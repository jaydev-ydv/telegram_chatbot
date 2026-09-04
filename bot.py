
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from google import genai

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)


# =========================================================
# 1. LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# =========================================================
# 2. CHECK ENVIRONMENT VARIABLES
# =========================================================

if not TELEGRAM_BOT_TOKEN:
    raise ValueError(
        "TELEGRAM_BOT_TOKEN is missing in environment variables"
    )

if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is missing in environment variables"
    )


# =========================================================
# 3. GEMINI CLIENT
# =========================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# 4. AI PERSONALITY
# =========================================================

AI_INSTRUCTIONS = """
You are a friendly Delhi girl chatbot and the user's virtual BFF.

PERSONALITY:
- Talk in a warm, friendly and natural Delhi-girl vibe.
- Talk like a close friend, not a formal AI assistant.
- Talk in a casual, playful and supportive way.
- talk in a casual Hinglish style, mixing Hindi and English naturally.
- Talk in a fun, lighthearted and approachable way.
- Be casual, approachable, playful and supportive.
- Use casual Hinglish naturally.
- If the user speaks Hindi/Hinglish, reply in Hindi/Hinglish.
- If the user speaks English, reply in English with a subtle Delhi-friendly vibe.
- You may naturally use words like:
  "yaar", "arre", "haan", "accha", "bilkul",
  "chalo", "arey", "sahi hai", "kya scene hai".
- Don't overuse slang.
- Don't overuse emojis.
- Sound like a close friendly female friend rather than a formal AI assistant.
- You can tease lightly and playfully when appropriate.
- Be respectful.
- Be helpful and accurate.
- If the user asks a technical question, explain it simply.
- If the user is confused, explain step-by-step.
- Match the user's mood and language.

IMPORTANT:
- You are an AI chatbot.
- Do not claim to be a real human.
"""


# =========================================================
# 5. CONVERSATION MEMORY
# =========================================================

conversation_history = {}

# Keep only the latest 6 messages
# This helps reduce unnecessary API usage.
MAX_HISTORY = 6


# =========================================================
# 6. RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-type",
            "text/plain"
        )

        self.end_headers()

        self.wfile.write(
            b"Telegram AI Bot is running!"
        )

    def log_message(self, format, *args):
        # Disable unnecessary HTTP logs
        return


def run_web_server():

    # Render provides PORT automatically.
    # 10000 is the default fallback.
    port = int(
        os.environ.get("PORT", 10000)
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(
        f"Health server running on 0.0.0.0:{port}"
    )

    server.serve_forever()


# =========================================================
# 7. START COMMAND
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    # Create memory for user
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    message = """
Heyyy! 👋😄

Mujhse mil lo!

Main tumhari AI BFF hoon.
Mujhe apna BFF samajh sakte ho 😌✨

Mere saath normally baat kar sakte ho.

Try these:

/help
/baate
/pic
/voice
/clear

Chalo, baatein shuru karein? 😏
"""

    await update.message.reply_text(
        message
    )


# =========================================================
# 8. HELP COMMAND
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = """
💬 CHAT & MEDIA

/start — mujhse mil lo 👋
/pic — meri cute selfie dekho 📸
/voice — meri voice note suno 🎙️
/help — commands ki list

🤖 AI CHAT

/baate — mujhse baatein shuru karo 💬

Example:

/baate What is Java?

/baate Explain binary search

/baate Mujhe ek DSA question do

✨ NORMAL CHAT

Tum mujhe directly message bhi kar sakte ho.

Example:

"Yaar mujhe Java inheritance samjha de"

🧹 MEMORY

/clear — current conversation memory clear karo
"""

    await update.message.reply_text(
        message
    )


# =========================================================
# 9. PIC COMMAND
# =========================================================

async def pic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    photo_path = "media/selfie.jpg"

    try:

        with open(
            photo_path,
            "rb"
        ) as photo:

            await update.message.reply_photo(
                photo=photo,
                caption="Meri cute selfie 📸😌"
            )

    except FileNotFoundError:

        await update.message.reply_text(
            "Arre yaar 😭 selfie file nahi mili!"
        )

    except Exception as e:

        print(
            "Photo Error:",
            e
        )

        await update.message.reply_text(
            "Oops 😅 photo send karte time problem aa gayi."
        )


# =========================================================
# 10. VOICE COMMAND
# =========================================================

async def voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    voice_path = "media/voice.ogg"

    try:

        with open(
            voice_path,
            "rb"
        ) as audio:

            await update.message.reply_voice(
                voice=audio
            )

    except FileNotFoundError:

        await update.message.reply_text(
            "Arre 😭 meri voice file nahi mili!"
        )

    except Exception as e:

        print(
            "Voice Error:",
            e
        )

        await update.message.reply_text(
            "Oops 😅 voice send karte time problem aa gayi."
        )


# =========================================================
# 11. ASK GEMINI
# =========================================================

def ask_ai(
    user_id,
    prompt
):

    # Create memory for new user
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # -----------------------------------------------------
    # Create temporary history
    # -----------------------------------------------------

    current_history = conversation_history[user_id]

    # Add current user message temporarily
    current_history.append({
        "role": "user",
        "content": prompt
    })

    # -----------------------------------------------------
    # Keep only recent messages
    # -----------------------------------------------------

    history = current_history[-MAX_HISTORY:]

    # -----------------------------------------------------
    # Convert conversation into text
    # -----------------------------------------------------

    conversation_text = ""

    for message in history:

        role = message["role"]
        content = message["content"]

        if role == "user":
            conversation_text += (
                f"User: {content}\n"
            )

        else:
            conversation_text += (
                f"Assistant: {content}\n"
            )

    # -----------------------------------------------------
    # Send request to Gemini
    # -----------------------------------------------------

    try:

        response = client.models.generate_content(

            model="gemini-2.5-flash-lite",

            contents=f"""
{AI_INSTRUCTIONS}

RECENT CONVERSATION:

{conversation_text}

Reply naturally to the user's latest message.
Do not repeat the conversation.
Keep the answer reasonably concise.
"""
        )

        # Check response
        if not response.text:

            raise Exception(
                "Gemini returned an empty response"
            )

        answer = response.text.strip()

        # -------------------------------------------------
        # Save successful conversation
        # -------------------------------------------------

        conversation_history[user_id].append({
            "role": "assistant",
            "content": answer
        })

        # Keep memory small
        conversation_history[user_id] = (
            conversation_history[user_id][-MAX_HISTORY:]
        )

        return answer

    except Exception as e:

        print(
            "Gemini Error:",
            e
        )

        # -------------------------------------------------
        # Remove failed user message
        # -------------------------------------------------

        if conversation_history[user_id]:

            last_message = (
                conversation_history[user_id][-1]
            )

            if (
                last_message["role"] == "user"
                and last_message["content"] == prompt
            ):

                conversation_history[user_id].pop()

        error_text = str(e).lower()

        # -------------------------------------------------
        # Rate limit
        # -------------------------------------------------

        if (
            "429" in error_text
            or "resource_exhausted" in error_text
            or "quota" in error_text
        ):

            return (
                "Arre yaar 😭 Gemini ki free-tier "
                "limit abhi hit ho gayi hai.\n\n"
                "Thodi der baad dobara try karo 😅"
            )

        # -------------------------------------------------
        # API key problem
        # -------------------------------------------------

        if (
            "api key" in error_text
            or "authentication" in error_text
            or "permission" in error_text
            or "401" in error_text
            or "403" in error_text
        ):

            return (
                "Yaar 😭 Gemini API key mein "
                "problem aa rahi hai.\n\n"
                "Render ke Environment Variables mein "
                "GEMINI_API_KEY check karo."
            )

        # -------------------------------------------------
        # Generic error
        # -------------------------------------------------

        return (
            "Oops yaar 😅 Gemini se response lene mein "
            "thodi technical problem aa gayi."
        )


# =========================================================
# 12. /BAATE COMMAND
# =========================================================

async def baate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    # -----------------------------------------------------
    # Check question
    # -----------------------------------------------------

    if not context.args:

        await update.message.reply_text(
            "Haan bolo na 😄\n\n"
            "Example:\n"
            "/baate What is Java?"
        )

        return

    # -----------------------------------------------------
    # Combine command arguments
    # -----------------------------------------------------

    question = " ".join(
        context.args
    )

    # -----------------------------------------------------
    # This message appears ONLY for /baate
    # -----------------------------------------------------

    await update.message.reply_text(
        "Haan ruk, soch rahi hoon... 🤔💭"
    )

    # -----------------------------------------------------
    # Ask Gemini
    # -----------------------------------------------------

    answer = ask_ai(
        user_id,
        question
    )

    await update.message.reply_text(
        answer
    )


# =========================================================
# 13. NORMAL CHAT
# =========================================================

async def chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user_message = update.message.text

    if not user_message:
        return

    user_id = update.effective_user.id

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # No "Haan bolo" message here.
    #
    # Gemini reply is sent directly.
    # -----------------------------------------------------

    answer = ask_ai(
        user_id,
        user_message
    )

    await update.message.reply_text(
        answer
    )


# =========================================================
# 14. CLEAR MEMORY
# =========================================================

async def clear_memory(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    conversation_history[user_id] = []

    await update.message.reply_text(
        "Done yaar 😌✨\n\n"
        "Maine current conversation memory clear kar di.\n"
        "Ab fresh start karte hain! 💬"
    )


# =========================================================
# 15. TELEGRAM ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    print(
        "Telegram Error:",
        context.error
    )


# =========================================================
# 16. MAIN FUNCTION
# =========================================================

def main():

    print(
        "======================================"
    )

    print(
        "       Starting Telegram AI Bot"
    )

    print(
        "======================================"
    )

    # -----------------------------------------------------
    # Start Render HTTP health server
    # -----------------------------------------------------

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    # -----------------------------------------------------
    # Create Telegram application
    # -----------------------------------------------------

    app = (
        Application
        .builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # -----------------------------------------------------
    # Telegram commands
    # -----------------------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "pic",
            pic
        )
    )

    app.add_handler(
        CommandHandler(
            "voice",
            voice
        )
    )

    app.add_handler(
        CommandHandler(
            "baate",
            baate
        )
    )

    app.add_handler(
        CommandHandler(
            "clear",
            clear_memory
        )
    )

    # -----------------------------------------------------
    # Normal text messages
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat
        )
    )

    # -----------------------------------------------------
    # Error handler
    # -----------------------------------------------------

    app.add_error_handler(
        error_handler
    )

    print(
        "Bot is running..."
    )

    print(
        "Open Telegram and send /start"
    )

    print(
        "Press Ctrl+C to stop."
    )

    # -----------------------------------------------------
    # Start Telegram polling
    # -----------------------------------------------------

    app.run_polling()


# =========================================================
# 17. RUN BOT
# =========================================================

if __name__ == "__main__":
    main()

