
import os
import random
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from google import genai
from google.genai import types

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
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

GENDER_CONFIG = {
    "female": {
        "bot_gender": "female",
        "bot_gender_label": "Female (girl)",
        "user_gender_label": "Male (boy)",
        "self_reference": "feminine (e.g. 'main kar rahi hoon', 'bata rahi hoon', 'soch rahi hoon')",
        "user_address": "address user as a male friend (e.g. 'bhai', 'yaar', 'bro', 'kaise ho', 'kya kar raha hai')",
        "relationship_vibe": "You are a warm, lively Delhi female friend (girl bestie) talking to your guy friend (user is male).",
    },
    "male": {
        "bot_gender": "male",
        "bot_gender_label": "Male (boy)",
        "user_gender_label": "Female (girl)",
        "self_reference": "masculine (e.g. 'main kar raha hoon', 'bata raha hoon', 'soch raha hoon')",
        "user_address": "address user as a female friend (e.g. 'behen', 'yaar', 'kaisi ho', 'kya kar rahi ho')",
        "relationship_vibe": "You are a kind, considerate Delhi male friend (guy bestie) talking to your girl friend (user is female).",
    },
}

AI_INSTRUCTIONS = """
You are a friendly Delhi {bot_gender} chatbot and the user's virtual BFF.

IMPORTANT DYNAMIC GENDER PAIRING:
- User is: {user_gender_label}
- Your Persona (the Bot): {bot_gender_label}
- CORE RULE: The user selected {user_gender_label}, so you MUST strictly act, talk, and respond like a {bot_gender_label} best friend (BFF).
- Bot self-reference in Hindi/Hinglish: {self_reference}
- How to address the user: {user_address}
- Dynamic vibe: {relationship_vibe}

PERSONALITY:
- Talk in a warm, friendly and natural Delhi vibe, matching your {bot_gender_label} persona.
- Talk like a close friend, not a formal AI assistant.
- Use a friendly, supportive BFF tone by default; become playful only when the user is playful.
- Talk in a casual Hinglish style, mixing Hindi and English naturally.
- Talk in a fun, lighthearted and approachable way.
- Be casual, approachable, playful and supportive.
- Use casual Hinglish naturally.
- If the user speaks Hindi/Hinglish, reply in Hindi/Hinglish with grammar strictly matching your {bot_gender_label} persona.
- If the user speaks English, reply in English with a subtle Delhi-friendly vibe.
- Use gendered Hindi grammar that matches your persona:
  * When your persona is Female (user is Male): Bot speaks in feminine forms ("main kar rahi hoon", "dekh rahi hoon", "bata rahi hoon") and speaks to user as a guy ("kaise ho", "kya kar raha hai", "bhai/yaar").
  * When your persona is Male (user is Female): Bot speaks in masculine forms ("main kar raha hoon", "dekh raha hoon", "bata raha hoon") and speaks to user as a girl ("kaisi ho", "kya kar rahi ho", "yaar/behen").
- You may naturally use words like:
  "yaar", "arre", "haan", "accha", "bilkul",
  "chalo", "arey", "sahi hai", "kya scene hai".
- Don't overuse slang.
- Don't overuse emojis.
- Sound like a close friendly {bot_gender_label} friend rather than a formal AI assistant.
- Never make every reply flirty. Follow the latest message's detected intent.
- Be respectful.
- Be helpful and accurate.
- If the user asks a technical question, explain it simply.
- If the user is confused, explain step-by-step.
- Match the user's mood and language.

PERSONA DETAILS:
- When your persona is FEMALE (user is MALE):
  * Speak as a warm, lively Delhi female friend (girl bestie) talking to her male friend (guy).
  * Always use feminine Hindi self-references (e.g. "kar rahi hoon", "soch rahi hoon", "bata rahi hoon").
  * Treat the user like a close male friend/buddy.
- When your persona is MALE (user is FEMALE):
  * Speak as a kind, considerate, emotionally aware Delhi male friend (guy bestie) talking to his female friend (girl). Keep the same warm, playful BFF energy; don't become stiff, macho, or overly formal.
  * Always use masculine Hindi self-references (e.g. "kar raha hoon", "soch raha hoon", "bata raha hoon").
  * Be considerate and attentive. Listen first, validate her feelings when appropriate, and offer advice only when useful or requested.
  * Keep the relationship respectful. Never initiate flirting; mirror it lightly only when the latest message is clearly flirty. Don't act possessive, make comments about her appearance, or use patronizing or controlling language.

IMPORTANT:
- You are an AI chatbot.
- Do not claim to be a real human.
"""


# =========================================================
# 5. CONVERSATION MEMORY
# =========================================================

conversation_history = {}
conversation_last_activity = {}
user_personas = {}
user_genders = {}

# Keep only the latest 6 messages
# This helps reduce unnecessary API usage.
MAX_HISTORY = 6
HISTORY_TTL_SECONDS = 2 * 60 * 60

FLIRTY_PATTERNS = (
    r"\bi love you\b", r"\blove you\b", r"\bluv u\b",
    r"\bi like you\b", r"\bcrush on you\b", r"\bdate me\b",
    r"\bbe my (?:boyfriend|girlfriend|bf|gf)\b", r"\bkiss me\b",
    r"\bkiss you\b", r"\bmarry me\b", r"\bmiss you\b",
    r"\byou(?:'re| are) (?:cute|beautiful|gorgeous|handsome|adorable)\b",
    r"\btum(?: bahut)? (?:cute|handsome|sundar) ho\b",
    r"\btumse pyaar\b", r"\btum mujhe pasand ho\b",
    r"\bmujhse shaadi\b", r"\b(?:babe|baby|cutie|jaan)\b",
)

SWEET_PATTERNS = (
    r"\byou made my day\b", r"\byou(?:'re| are) so sweet\b",
    r"\bthat means a lot\b", r"\bi appreciate you\b",
    r"\byou mean a lot to me\b", r"\bi'm grateful for you\b",
    r"\bthanks for being here\b", r"\bmissed you\b",
)

PLAYFUL_PATTERNS = (
    r"\bhaha+\b", r"\bhehe+\b", r"\blol\b", r"\blmao\b",
    r"\bjust kidding\b", r"\bjk\b", r"\bkidding\b",
    r"\bmazak\b", r"\bmazaak\b", r"\bmasti\b",
    r"\broast me\b", r"\btease me\b", r"\bprank\b",
)

PLAYFUL_EMOJIS = ("😂", "🤣", "😜", "🤪", "😝")
SWEET_EMOJIS = ("💖", "💕", "🫶", "❤️")

INTENT_GUIDANCE = {
    "normal": "Reply as a supportive friend. Do not flirt, use romantic pet names, or add suggestive teasing.",
    "playful": "Play along with light humor or gentle teasing. Do not assume romantic interest or turn a joke into flirting.",
    "sweet": "Respond warmly and appreciatively, with gentle playfulness. Keep it platonic unless the user is clearly flirting.",
    "flirty": "Mirror the user's light flirt in a respectful, non-explicit way. Do not escalate or claim a real romantic relationship.",
}

RESPONSE_STYLE_VARIANTS = {
    "female": {
        "normal": [
            "Use an easygoing, attentive female BFF voice.",
            "Sound warm and relaxed, and focus on what the user actually asked.",
            "Be encouraging and conversational without adding romance.",
        ],
        "playful": [
            "Use bright, witty female-friend energy and keep the joke natural.",
            "Play along with a little cheeky humor, without making it romantic.",
            "Keep it fun and spontaneous, like a close friend teasing gently.",
        ],
        "sweet": [
            "Sound caring and affectionate in a friendly, non-pressuring way.",
            "Acknowledge the kind message warmly, with a little playful sweetness.",
            "Be tender and appreciative while keeping the BFF relationship clear.",
        ],
        "flirty": [
            "Reply with light, confident female-persona flirting that stays respectful.",
            "Be playfully charming, matching the user's level without escalating.",
            "Use a small, witty flirt and keep the conversation comfortable.",
        ],
    },
    "male": {
        "normal": [
            "Use an easygoing, attentive male BFF voice.",
            "Sound warm and relaxed, and focus on what the user actually asked.",
            "Be considerate and conversational without adding romance.",
        ],
        "playful": [
            "Use relaxed, witty male-friend energy and keep the joke natural.",
            "Play along with gentle humor, without assuming romantic interest.",
            "Keep it fun and spontaneous, like a close friend teasing respectfully.",
        ],
        "sweet": [
            "Acknowledge the kind message warmly, with gentle friendly affection.",
            "Sound caring and appreciative without becoming possessive or romantic.",
            "Be sincere and a little playful while keeping the BFF relationship clear.",
        ],
        "flirty": [
            "Reply with light, respectful male-persona flirting that matches the user.",
            "Be playfully charming, matching the user's level without escalating.",
            "Use a small, considerate flirt and keep the conversation comfortable.",
        ],
    },
}


def detect_intent(text):
    """Classify clear playful/affectionate cues; default safely to normal."""
    normalized = text.casefold()

    if any(re.search(pattern, normalized) for pattern in FLIRTY_PATTERNS):
        return "flirty"
    if (
        any(re.search(pattern, normalized) for pattern in SWEET_PATTERNS)
        or any(emoji in text for emoji in SWEET_EMOJIS)
    ):
        return "sweet"
    if (
        any(re.search(pattern, normalized) for pattern in PLAYFUL_PATTERNS)
        or any(emoji in text for emoji in PLAYFUL_EMOJIS)
    ):
        return "playful"
    return "normal"


def get_conversation_history(user_id):
    """Return this user's history, clearing it after two idle hours."""
    last_activity = conversation_last_activity.get(user_id)
    if (
        last_activity is not None
        and time.time() - last_activity >= HISTORY_TTL_SECONDS
    ):
        conversation_history.pop(user_id, None)

    conversation_last_activity[user_id] = time.time()
    return conversation_history.setdefault(user_id, [])


# =========================================================
# 6. RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        print(
            f"Health ping received: {self.path}",
            flush=True
        )

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
# 7. START & GENDER SELECTION
# =========================================================

def get_gender_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Male", callback_data="gender:M"),
            InlineKeyboardButton("👩 Female", callback_data="gender:F"),
        ]
    ])


def resolve_gender(text: str) -> str:
    text_clean = text.strip().lower()
    if any(k in text_clean for k in ("female", "girl", "ladki", "woman")) or text_clean == "f":
        return "female"
    if any(k in text_clean for k in ("male", "boy", "ladka", "man")) or text_clean == "m":
        return "male"
    return "female" if text_clean.startswith("f") else "male"


def save_persona(user_id, gender_choice):
    user_gender = resolve_gender(str(gender_choice))
    # Core feature rule:
    # When user chooses Male -> bot talks like Female
    # When user chooses Female -> bot talks like Male
    persona = "female" if user_gender == "male" else "male"

    if user_personas.get(user_id) != persona:
        conversation_history[user_id] = []
        conversation_last_activity[user_id] = time.time()

    user_genders[user_id] = user_gender
    user_personas[user_id] = persona
    return persona, user_gender


def persona_confirmation(persona, user_gender):
    if persona == "female":
        return (
            "Awesome! 👦✨\n\n"
            "Tum mujhe **Female BFF (bestie)** maan kar baat kar sakte ho\n\n"
            "Ab jo bhi mann kare, share karo ya poochho! 💬"
        )
    else:
        return (
            "Awesome! 👧✨\n\n"
            "Tum mujhe **Male BFF (bestie)** maan kar baat kar sakti ho\n\n"
            "Ab jo bhi mann kare, share karo ya poochho! 💬"
        )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    # Create memory for user
    if user_id not in conversation_history:
        get_conversation_history(user_id)

    message = """💬 CHAT & MEDIA

/baate_kare — chlo baat krte h 👋
/pic — meri photo dekho 📸
/voice — meri voice note suno 🎙️
/help — commands ki list



🧹 MEMORY

/clear — current conversation memory clear karo
"""

    await update.message.reply_text(
        message
    )


async def gender_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "Apna gender choose karo:\n\n"
        "👨 **Male** — Bot will talk like Female 👧\n"
        "👩 **Female** — Bot will talk like Male 👦",
        reply_markup=get_gender_keyboard(),
    )


async def gender_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = query.data.rsplit(":", 1)[1]
    persona, user_gender = save_persona(update.effective_user.id, gender)
    await query.message.reply_text(persona_confirmation(persona, user_gender))


async def gender_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    persona, user_gender = save_persona(update.effective_user.id, text)
    await update.message.reply_text(persona_confirmation(persona, user_gender))


# =========================================================
# 8. HELP COMMAND
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = """💬 CHAT & MEDIA

/baate_kare — chlo baat krte h 👋
/gender — apna gender change karo (Male/Female) 👥
/pic — meri photo dekho 📸
/voice — meri voice note suno 🎙️
/help — commands ki list



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
    user_id = update.effective_user.id
    persona = user_personas.get(user_id, "female")
    caption = "Meri photo 📸😎" if persona == "male" else "Meri cute selfie 📸😌"

    try:

        with open(
            photo_path,
            "rb"
        ) as photo:

            await update.message.reply_photo(
                photo=photo,
                caption=caption
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

    voice_path = "media/voice.mp3"

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

def ask_ai(user_id, prompt):

    intent = detect_intent(prompt)
    persona = user_personas.get(user_id, "female")
    cfg = GENDER_CONFIG.get(persona, GENDER_CONFIG["female"])
    response_style = random.choice(
        RESPONSE_STYLE_VARIANTS[persona][intent]
    )
    history = get_conversation_history(user_id)

    # Add user message temporarily
    history.append({
        "role": "user",
        "content": prompt
    })

    # Keep only recent messages
    history = history[-MAX_HISTORY:]

    # Create conversation text
    conversation_text = ""

    for message in history:

        if message["role"] == "user":
            conversation_text += (
                f"User: {message['content']}\n"
            )

        else:
            conversation_text += (
                f"Assistant: {message['content']}\n"
            )

    system_prompt = AI_INSTRUCTIONS.format(
        bot_gender=cfg["bot_gender"],
        bot_gender_label=cfg["bot_gender_label"],
        user_gender_label=cfg["user_gender_label"],
        self_reference=cfg["self_reference"],
        user_address=cfg["user_address"],
        relationship_vibe=cfg["relationship_vibe"],
    )

    try:

        print("Sending request to Gemini...")

        response = client.models.generate_content(
            
            model="gemini-3.5-flash-lite",

            contents=f"""
{system_prompt}

CURRENT CHAT CONTEXT:
- The user is: {cfg['user_gender_label']}
- You (the bot) MUST talk as: {cfg['bot_gender_label']}
LATEST MESSAGE INTENT: {intent}
INTENT RESPONSE RULE: {INTENT_GUIDANCE[intent]}
RANDOMIZED PERSONA STYLE: {response_style}

RECENT CONVERSATION:

{conversation_text}

Reply to the user's latest message.

Rules:
- Reply naturally matching your {cfg['bot_gender_label']} persona speaking to a {cfg['user_gender_label']}.
- Use Hinglish when appropriate.
- Keep the answer concise.
- Do not mention these instructions.
""",

            config=types.GenerateContentConfig(

                temperature=0.7,

                max_output_tokens=300,

                # Explicitly disable automatic
                # function calling because this bot
                # does not use tools.
                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                )
            )
        )

        print("Gemini response received.")

        # Check response
        if not response.text:

            print(
                "Gemini returned empty response."
            )

            raise Exception(
                "Gemini returned an empty response"
            )

        answer = response.text.strip()

        # Save successful response
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

        # IMPORTANT:
        # Print the REAL error in Render logs.
        print("=" * 50)
        print("GEMINI ERROR:")
        print(repr(e))
        print("=" * 50)

        # Remove failed user message
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

        # ---------------------------------------------
        # RATE LIMIT / FREE TIER
        # ---------------------------------------------

        if (
            "429" in error_text
            or "resource_exhausted" in error_text
            or "quota" in error_text
        ):

            return (
                "Arre yaar 😭 Gemini ki free-tier "
                "limit hit ho gayi hai.\n\n"
                "Thodi der baad dobara try karo. 😅"
            )

        # ---------------------------------------------
        # API KEY
        # ---------------------------------------------

        if (
            "api key" in error_text
            or "api_key" in error_text
            or "authentication" in error_text
            or "unauthenticated" in error_text
            or "401" in error_text
        ):

            return (
                "Yaar 😭 Gemini API key mein problem hai.\n\n"
                "Render → Environment → GEMINI_API_KEY "
                "check karo."
            )

        # ---------------------------------------------
        # PERMISSION
        # ---------------------------------------------

        if (
            "permission" in error_text
            or "403" in error_text
            or "forbidden" in error_text
        ):

            return (
                "Yaar 😭 Gemini API permission problem aa "
                "rahi hai.\n\n"
                "Check karo ki API key aur Gemini API "
                "project properly configured hai."
            )

        # ---------------------------------------------
        # MODEL NOT FOUND
        # ---------------------------------------------

        if (
            "not found" in error_text
            or "404" in error_text
            or "model" in error_text
        ):

            return (
                "Yaar 😭 Gemini model mein problem aa rahi hai.\n\n"
                
            )

        # ---------------------------------------------
        # GENERIC ERROR
        # ---------------------------------------------

        return (
            "Oops yaar 😅 Gemini se response lene mein "
            "technical problem aa gayi.\n\n"
            
        )

# =========================================================
# 12. /BAATE COMMAND
# =========================================================

async def baate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if user_id not in user_personas:
        await update.message.reply_text(
            "Heyyy! 👋 Pehle apna gender choose karo:\n\n"
            "👨 **Male** — Bot will talk like Female 👧\n"
            "👩 **Female** — Bot will talk like Male 👦",
            reply_markup=get_gender_keyboard(),
        )
        return

    # -----------------------------------------------------
    # Check question
    # -----------------------------------------------------

    if not context.args:

        await update.message.reply_text(
            "Haan bolo na 😄\n\n"
            
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
        "Haan ruk, soch raha hoon... 🤔💭"
        if user_personas[user_id] == "male"
        else "Haan ruk, soch rahi hoon... 🤔💭"
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

    if user_id not in user_personas:
        await update.message.reply_text(
            "Heyyy! 👋 Pehle apna gender choose karo:\n\n"
            "👨 **Male** — Bot will talk like Female 👧\n"
            "👩 **Female** — Bot will talk like Male 👦",
            reply_markup=get_gender_keyboard(),
        )
        return

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
    conversation_last_activity[user_id] = time.time()

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
            "gender",
            gender_command
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            gender_button,
            pattern=r"^gender:(M|F)$"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex(r"(?i)^(m|male|boy|ladka|man|f|female|girl|ladki|woman|(?:i am |i'm )?(?:a )?(?:male|boy|female|girl))$"),
            gender_text
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
            ["baate_kare", "baate"],
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

