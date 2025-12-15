import os
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ===== ENV =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or "0")

# ===== TIMEZONE =====
TZ = ZoneInfo("Europe/Minsk")
WD_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# ===== STORAGE (in-memory) =====
ADMIN_SLOTS = {}           # date_iso -> (start_min, end_min)
USER_SLOTS = {}            # user_id -> {date_iso -> (start_min, end_min)}

# ===== TEXTS =====
QUESTION_TEXT = (
    "Привет! Раз ты здесь, значит ты посмеялась или улыбнулась, "
    "но чтобы убедиться, что ты попала сюда не просто так, ответь на вопрос:\n\n"
    "как зовут собаку, которая сначала молчит и кажется милой, "
    "а потом начинает тянуть как танк?"
)

AFTER_CODEWORD_TEXT = (
    "Закончили с прелюдиями, можно переходить на конкретику.\n\n"
    "Напиши команду /slots"
)

FINAL_TEXT = (
    "Чудесно, жду тебя в это время по адресу:\n"
    "Дорошевича 4, подъезд 3, этаж 3, квартира 49.\n\n"
    "Яндекс Карты:\n"
    "https://yandex.ru/maps?text=53.918795,27.588825&si=f8fwk7wvw7hmh0cac49347aqmw"
)

ACCEPTED_ANSWERS = {"пуф", "пуфф"}
MAX_TRIES = 2

# ===== STATES =====
WAIT_ANSWER = 0
S_WEEK, S_DAY, S_START, S_END, S_AFTER_SAVE = range(10, 15)
PICK_INTERSECTION = 30

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# ===== HELPERS =====
def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

def now_date():
    return datetime.now(TZ).date()

def monday(d: date):
    return d - timedelta(days=d.weekday())

def fmt_day(d: date):
    return f"{d:%d.%m} {WD_RU[d.weekday()]}"

def to_min(hhmm: str):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m

def from_min(x: int):
    return f"{x//60:02d}:{x%60:02d}"


# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["tries"] = 0
    await update.message.reply_text(QUESTION_TEXT)
    return WAIT_ANSWER


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.lower().strip()
    context.user_data["tries"] += 1

    if txt in ACCEPTED_ANSWERS:
        await update.message.reply_text(AFTER_CODEWORD_TEXT)
        return ConversationHandler.END

    if context.user_data["tries"] >= MAX_TRIES:
        await update.message.reply_text("Неверно. Доступ закрыт.")
        return ConversationHandler.END

    await update.message.reply_text("Неверно. Попробуй ещё раз:")
    return WAIT_ANSWER


# ===== /slots =====
async def slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["admin"] = is_admin(update)
    kb = [
        [InlineKeyboardButton("Эта неделя", callback_data="week:this")],
        [InlineKeyboardButton("Следующая неделя", callback_data="week:next")],
    ]
    await update.message.reply_text("Про какую неделю говорим?", reply_markup=InlineKeyboardMarkup(kb))
    return S_WEEK


async def pick_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    base = monday(now_date())
    if q.data.endswith("next"):
        base += timedelta(days=7)

    context.user_data["week"] = base.isoformat()

    buttons = []
    row = []
    for i in range(7):
        d = base + timedelta(days=i)
        if d < now_date():
            continue
        row.append(InlineKeyboardButton(fmt_day(d), callback_data=f"day:{d.isoformat()}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await q.edit_message_text("Выбери день:", reply_markup=InlineKeyboardMarkup(buttons))
    return S_DAY


async def pick_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    context.user_data["date"] = q.data.split(":")[1]
    await q.edit_message_text("Напиши время начала (hh:mm)")
    return S_START


async def pick_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TIME_RE.match(update.message.text):
        await update.message.reply_text("Формат hh:mm")
        return S_START

    context.user_data["start"] = to_min(update.message.text)
    await update.message.reply_text("Напиши время окончания (hh:mm)")
    return S_END


async def pick_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TIME_RE.match(update.message.text):
        await update.message.reply_text("Формат hh:mm")
        return S_END

    end = to_min(update.message.text)
    start = context.user_data["start"]
    if end <= start:
        await update.message.reply_text("Окончание должно быть позже начала")
        return S_END

    d = context.user_data["date"]

    if context.user_data["admin"]:
        ADMIN_SLOTS[d] = (start, end)
        await update.message.reply_text("Слот админа сохранён.")
        return ConversationHandler.END

    uid = update.effective_user.id
    USER_SLOTS.setdefault(uid, {})[d] = (start, end)

    if d in ADMIN_SLOTS:
        a_s, a_e = ADMIN_SLOTS[d]
        s = max(start, a_s)
        e = min(end, a_e)
        if e > s:
            await update.message.reply_text(FINAL_TEXT)
            return ConversationHandler.END

    await update.message.reply_text("Слот сохранён. Пересечений пока нет.")
    return ConversationHandler.END


# ===== MAIN =====
async def post_init(app: Application):
    await app.bot.delete_webhook(drop_pending_updates=True)


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={WAIT_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, answer)]},
            fallbacks=[CommandHandler("start", start)],
        )
    )

    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("slots", slots)],
            states={
                S_WEEK: [CallbackQueryHandler(pick_week)],
                S_DAY: [CallbackQueryHandler(pick_day)],
                S_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, pick_start)],
                S_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, pick_end)],
            },
            fallbacks=[CommandHandler("slots", slots)],
        )
    )

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
