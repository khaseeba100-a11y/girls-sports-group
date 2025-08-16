import os, logging, re, pathlib, json
from datetime import datetime
from typing import Dict, Any, Optional
from time import time

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, Voice
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ===== إعدادات عامة =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN    = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# رابط WhatsApp Community: من ENV لو موجود وإلا الافتراضي تحت
COMMUNITY_LINK = os.getenv(
    "COMMUNITY_LINK",
    "https://chat.whatsapp.com/KW0DgEUvhMII6r02a55gEL?mode=ems_copy_c"
)

os.makedirs("voices", exist_ok=True)
os.makedirs("state", exist_ok=True)  # لتخزين اللغة

STATE_FILE = pathlib.Path("state") / "users_lang.json"

# ===== تحميل/حفظ الحالة =====
def load_state() -> Dict[str, str]:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(data: Dict[str, str]) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Couldn't save state: {e}")

users_lang: Dict[str, str] = load_state()  # { "12345": "ar" }

# ===== نصوص اللغتين =====
AR_WELCOME = (
    "يامرحبا فيــج 🙋🏻‍♀️\n"
    "Girls Sports Group | قروب رياضي نسائي نشارك فيه أنشطتنا الرياضية وانتي تقدرين تشاركين نشاطج مع البنات\n\n"
    "الرابط يضيفج على الـ community الخاصة في القروب وفيها يظهر الـ٨ قنوات لكل إمارة "
    "وانتي تطلبين الانضمام لإمارتج فقط.\n\n"
    "بحيث يكون عندج صفحة الـannouncement الخاصة في القروب بالإضافة لقروب إمارتج.\n\n"
    "❗️مهم:\n"
    "- تطلعين على القوانين\n"
    "- تنضمين لقروب إمارة واحدة فقط\n\n"
    "🎀 رابط الواتساب:\n"
    "{community}"
)

EN_WELCOME = (
    "Hello 🙋🏻‍♀️\n"
    "Girls Sports Group — a women’s sports community where we share activities together.\n\n"
    "This link takes you to our WhatsApp Community with 8 groups (one per Emirate).\n"
    "Please request to join your Emirate only.\n\n"
    "You’ll have an announcements page + your Emirate group.\n\n"
    "❗️Important:\n"
    "- Read the rules\n"
    "- Join only ONE Emirate group\n\n"
    "🎀 WhatsApp link:\n"
    "{community}"
)

LANG_PICK_TEXT = "اختاري لغتج / Choose your language:"
EMIRATE_QUESTION_AR = "سجّلي فويس ≤ 30 ثانية: قولي اسمج والإمارة اللي تسكنين فيها."
EMIRATE_QUESTION_EN = "Please record a short voice (≤ 30s): say your name and which Emirate you live in."
CONFIRM_AR = "تم استلام الفويس ✅ بنرسل لج المشرف للمراجعة."
CONFIRM_EN = "Voice received ✅ We’ll send it to the moderator for review."

EMIRATES_AR = ["أبوظبي","دبي","الشارقة","عجمان","أم القيوين","رأس الخيمة","الفجيرة","العين"]
EMIRATE_REGEX = "|".join([re.escape(e) for e in EMIRATES_AR])

# ===== مانع تكرار =====
recent_lang_set: Dict[int, float] = {}

def t(lang: str, ar: str, en: str) -> str:
    return ar if lang == "ar" else en

# ===== أوامر =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[
        InlineKeyboardButton("العربية 🇦🇪", callback_data="lang_ar"),
        InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")
    ]]
    await update.message.reply_text(LANG_PICK_TEXT, reply_markup=InlineKeyboardMarkup(buttons))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسلي /start لاختيار اللغة ثم سجّلي فويس. /start to choose language, then send a short voice.")

# ===== اختيار اللغة (مع مانع تكرار + تخزين) =====
async def select_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    now = time()
    if now - recent_lang_set.get(user_id, 0) < 10:
        return
    recent_lang_set[user_id] = now

    lang = "ar" if query.data == "lang_ar" else "en"

    # خزّني اللغة في الذاكرة والملف
    users_lang[str(user_id)] = lang
    save_state(users_lang)

    await query.edit_message_text("تم اختيار العربية ✅" if lang == "ar" else "English selected ✅")
    await query.message.reply_text(EMIRATE_QUESTION_AR if lang == "ar" else EMIRATE_QUESTION_EN)

# ===== استقبال الفويس =====
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    voice: Optional[Voice] = update.message.voice

    # حاول نجيب اللغة من الذاكرة/الملف
    lang = users_lang.get(str(user_id))
    if not lang:
        buttons = [[
            InlineKeyboardButton("العربية 🇦🇪", callback_data="lang_ar"),
            InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")
        ]]
        await update.message.reply_text(LANG_PICK_TEXT, reply_markup=InlineKeyboardMarkup(buttons))
        return

    # تحميل الفويس
    file = await context.bot.get_file(voice.file_id)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{user_id}_{ts}.ogg"
    path = pathlib.Path("voices") / safe_name
    await file.download_to_drive(custom_path=str(path))

    # محاولة اكتشاف الإمارة من الكابتشن (اختياري)
    caption = (update.message.caption or "").strip()
    emirate_found = None
    if caption:
        m = re.search(EMIRATE_REGEX, caption)
        if m:
            emirate_found = m.group(0)

    # إشعار المستخدم (مصَحّحة "لج")
    await update.message.reply_text(CONFIRM_AR if lang == "ar" else CONFIRM_EN)

    # إرسال للأدمن مع أزرار الموافقة/الرفض + الفويس
    try:
        approve_btn = InlineKeyboardButton("موافقة ✅", callback_data=f"approve:{user_id}:{safe_name}")
        reject_btn  = InlineKeyboardButton("رفض ❌", callback_data=f"reject:{user_id}:{safe_name}")
        kb = InlineKeyboardMarkup([[approve_btn, reject_btn]])

        text = (
            f"طلب جديد من @{user.username or user_id}\n"
            f"اللغة: {lang}\n"
            f"التعليق: {caption or '—'}\n"
            f"الإمارة (تخمين): {emirate_found or 'غير محدد'}\n"
            f"ملف: {safe_name}"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=kb)
        with open(path, "rb") as f:
            await context.bot.send_voice(chat_id=ADMIN_ID, voice=f, caption="الرسالة الصوتية")
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")

# ===== موافقة/رفض الأدمن =====
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # approve:{uid}:{filename} أو reject:{uid}:{filename}

    action, uid_str, filename = data.split(":", 2)
    uid = int(uid_str)

    lang = users_lang.get(str(uid), "ar")

    if action == "approve":
        msg = (AR_WELCOME if lang == "ar" else EN_WELCOME).format(community=COMMUNITY_LINK)
        await context.bot.send_message(chat_id=uid, text=msg)
        await query.edit_message_text(f"✅ تمت الموافقة على {uid}.")
    else:
        msg = t(lang, "نعتذر، لم يتم القبول هذه المرة.", "Sorry, your request was not approved this time.")
        await context.bot.send_message(chat_id=uid, text=msg)
        await query.edit_message_text(f"❌ تم رفض {uid}.")

# ===== فلاتر النصوص =====
async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = users_lang.get(str(user_id))
    if not lang:
        await start(update, context)
        return
    await update.message.reply_text(EMIRATE_QUESTION_AR if lang == "ar" else EMIRATE_QUESTION_EN)

# ===== Main =====
def main():
    if not TOKEN:
        raise RuntimeError("Missing TOKEN env var")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(CallbackQueryHandler(select_lang, pattern=r"^lang_(ar|en)$"))
    app.add_handler(CallbackQueryHandler(admin_actions, pattern=r"^(approve|reject):"))

    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    logger.info("Bot is running (long polling)…")
    # لو requirements عندك 20.x استخدمي السطر تحت بدون باراميترات إضافية
    app.run_polling()

if __name__ == "__main__":
    main()
