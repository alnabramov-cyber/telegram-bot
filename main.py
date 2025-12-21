import os
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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0").strip() or "0")

# ===== TIMEZONE / DATES =====
TZ = ZoneInfo("Europe/Minsk")  # GMT+3
WD_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# Слоты по дню недели — ОТКЛЮЧЕНЫ
SLOTS_BY_WD = {
    0: [],
    1: [],
    2: [],
    3: [],
    4: [],
    5: [],
    6: [],
}

# Слоты "на сегодня" — ОТКЛЮЧЕНЫ
TODAY_SLOTS = []

# Слоты ТОЛЬКО по конкретным датам
SLOTS_BY_DATE = {
    "2025-12-21": ["После 16:00 и до 23:00"],  # воскресенье
    "2025-12-24": ["После 20:00"],             # среда
    "2025-12-25": ["После 15:00"],             # четверг
    "2025-12-26": ["После 15:00"],             # пятница
}


# ===== TEXTS =====
QUESTION_TEXT = (
    "Привет! Раз ты здесь, значит ты посмеялась или улыбнулась, "
    "но чтобы убедиться, что ты попала сюда не просто так, ответь на вопрос:\n\n"
    "как зовут собаку, которая сначала молчит и кажется милой, "
    "а потом начинает тянуть как танк?"
)

AFTER_OK_TEXT = (
    "Привет, Полина)\n\n"
    "Я хочу тебя касаться, доставлять тебе удовольствие и заняться с тобой сексом. "
    "Это прекрасно, не так ли?) Чтобы это произошло, выбери один из вариантов ниже:"
)

AFTER_RANDOM_TEXT = "Ты явно нажала случайно, поэтому выбери заново."
AFTER_YES_TEXT = "Прекрасно, я очень рад)\nВыбери день:"

YANDEX_MAPS_URL = "https://yandex.ru/maps?text=53.918795,27.588825&si=f8fwk7wvw7hmh0cac49347aqmw"

FINAL_TEXT = (
    "Чудесно, жду тебя в это время по адресу:\n"
    "Дорошевича 4, подъезд 3, этаж 3, квартира 49.\n\n"
    f"Яндекс Карты: {YANDEX_MAPS_URL}"
)

ACCEPTED_ANSWERS = {"пуф", "пуфф"}
MAX_TRIES = 2

# ===== STATES =====
WAIT_ANSWER, CHOICE, PICK_DAY, PICK_TIME = range(4)

# ===== KEYBOARDS =====
def choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Я тоже этого хочу", callback_data="choice:yes")],
        [InlineKeyboardButton("Теоретическая кнопка", callback_data="choice:random")],
    ])

def day_keyboard():
    today = datetime.now(TZ).date()
    buttons = []
    row = []

    # показываем ближайшие 14 дней; прошедшие не попадут
    for i in range(14):
        d = today + timedelta(days=i)
        wd = d.weekday()

        slots = TODAY_SLOTS if d == today else SLOTS_BY_WD.get(wd, [])
        if not slots:
            continue  # если слотов нет — день не показываем

        label = f"{d:%d.%m} {WD_RU[wd]}"     # 16.12 вт
        cb = f"day:{d.isoformat()}"          # day:2025-12-16

        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)

def time_keyboard(date_iso: str):
    today = datetime.now(TZ).date()
    d = date.fromisoformat(date_iso)

    if d < today:
        return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back:days")]])

    slots = SLOTS_BY_DATE.get(date_iso, [])

    buttons = [[InlineKeyboardButton(s, callback_data=f"time:{date_iso}:{s}")] for s in slots]
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back:days")])
    return InlineKeyboardMarkup(buttons)


# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["tries"] = 0
    await update.message.reply_text(QUESTION_TEXT)
    return WAIT_ANSWER

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    context.user_data["tries"] = int(context.user_data.get("tries", 0)) + 1

    if text in ACCEPTED_ANSWERS:
        await update.message.reply_text(AFTER_OK_TEXT, reply_markup=choice_keyboard())
        return CHOICE

    if context.user_data["tries"] >= MAX_TRIES:
        await update.message.reply_text("Неверно. Доступ закрыт.")
        return ConversationHandler.END

    await update.message.reply_text("Неверно. Попробуй еще раз:")
    return WAIT_ANSWER

async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "choice:random":
        await q.edit_message_text(AFTER_RANDOM_TEXT, reply_markup=choice_keyboard())
        return CHOICE

    if q.data == "choice:yes":
        await q.edit_message_text(AFTER_YES_TEXT, reply_markup=day_keyboard())
        return PICK_DAY

    return CHOICE

async def on_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    _, date_iso = q.data.split(":", 1)
    context.user_data["date_iso"] = date_iso

    await q.edit_message_text("Выбери время:", reply_markup=time_keyboard(date_iso))
    return PICK_TIME

async def on_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "back:days":
        await q.edit_message_text(AFTER_YES_TEXT, reply_markup=day_keyboard())
        return PICK_DAY

    _, date_iso, slot = q.data.split(":", 2)

    await q.edit_message_text(FINAL_TEXT, disable_web_page_preview=True)

    # notify admin
    if ADMIN_ID:
        user = q.from_user
        name = f"@{user.username}" if user.username else user.full_name

        d = date.fromisoformat(date_iso)
        date_label = f"{d:%d.%m} {WD_RU[d.weekday()]}"

        msg = (
            "Новая заявка:\n"
            f"Пользователь: {name}\n"
            f"День: {date_label}\n"
            f"Время: {slot}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
        except Exception:
            pass

    return ConversationHandler.END

# ===== IMPORTANT: remove webhook on startup (safe) =====
async def post_init(app: Application):
    await app.bot.delete_webhook(drop_pending_updates=True)

# ===== MAIN =====
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, answer)],
            CHOICE: [CallbackQueryHandler(on_choice)],
            PICK_DAY: [CallbackQueryHandler(on_day)],
            PICK_TIME: [CallbackQueryHandler(on_time)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
