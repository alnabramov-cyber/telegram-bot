import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== ENV =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()
ADMIN_CHAT_ID_INT = int(ADMIN_CHAT_ID) if ADMIN_CHAT_ID.isdigit() else None

# ===== TIME =====
TZ = ZoneInfo("Europe/Minsk")  # GMT+3
WD_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# Слоты по дню недели (0=пн ... 6=вс)
SLOTS_BY_WD = {
    0: [],                 # пн
    1: [],                 # вт
    2: [],                 # ср
    3: ["После 19:00"],    # чт
    4: ["После 20:00"],    # пт
    5: ["После 13:00"],    # сб
    6: ["После 13:00"],    # вс
}
TODAY_SLOTS = ["После концерта"]  # слоты именно "сегодня"

# Слоты по конкретной дате (YYYY-MM-DD). Имеют приоритет над SLOTS_BY_WD.
SLOTS_BY_DATE = {
    "2025-12-21": ["любое время"],  # вс
    "2025-12-24": ["После 20:00"],  # ср
    "2025-12-25": ["После 15:00"],  # чт
    "2025-12-26": ["После 15:00"],  # пт
}


# ===== TEXTS =====
QUESTION_TEXT = (
    "Привет! Раз ты здесь, значит ты посмеялась или улыбнулась, "
    "но чтобы убедиться, что ты попала сюда не просто так, ответь на вопрос:\n\n"
    "как зовут собаку, которая сначала молчит и кажется милой, "
    "а потом начинает тяфкать и превращает жизнь в ад?"
)

WRONG_ANSWER_TEXT = "Неа) Попробуй еще раз 🐶"

AFTER_OK_TEXT = (
    "Привет, Полина)\n\n"
    "Ты — прекрасна, не так ли?) Чтобы это произошло, выбери один из вариантов ниже:"
)

BUTTON_1_TEXT = "Давай, поугараем"
BUTTON_2_TEXT = "Я просто так сюда зашла"

AFTER_RANDOM_TEXT = (
    "Ну что ж)\n\n"
    "Чтобы мы могли вместе посмеяться и поугарать, выбери удобный день и время:"
)

AFTER_RANDOM_NO_SLOTS_TEXT = "Админ ещё не задал доступное время"

ADMIN_NOTIFY_TEXT = (
    "Новая заявка!\n\n"
    "Пользователь: {user}\n"
    "День: {day}\n"
    "Время: {time}\n"
)

CONFIRM_TEXT = (
    "Записал ✅\n\n"
    "Если хочешь выбрать другое время — нажми /start"
)

# ===== HELPERS =====
def now_dt() -> datetime:
    return datetime.now(TZ)

def today_date() -> date:
    return now_dt().date()

def fmt_day(d: date) -> str:
    return f"{WD_RU[d.weekday()]} {d.day:02d}.{d.month:02d}"

def build_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(BUTTON_1_TEXT, callback_data="action:random")],
        [InlineKeyboardButton(BUTTON_2_TEXT, callback_data="action:just")],
    ]
    return InlineKeyboardMarkup(buttons)

def build_days_keyboard() -> InlineKeyboardMarkup:
    today = today_date()
    rows = []

    for i in range(14):  # показываем максимум 14 дней вперед
        d = today + timedelta(days=i)
        wd = d.weekday()

        slots = TODAY_SLOTS if d == today else (SLOTS_BY_DATE.get(d.isoformat()) or SLOTS_BY_WD.get(wd, []))
        if not slots:
            continue  # если слотов нет — день не показываем

        rows.append([InlineKeyboardButton(fmt_day(d), callback_data=f"day:{d.isoformat()}")])

    if not rows:
        rows = [[InlineKeyboardButton(AFTER_RANDOM_NO_SLOTS_TEXT, callback_data="noop")]]

    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back:main")])
    return InlineKeyboardMarkup(rows)

def build_times_keyboard(date_iso: str) -> InlineKeyboardMarkup:
    today = today_date()

    try:
        d = datetime.strptime(date_iso, "%Y-%m-%d").date()
    except ValueError:
        return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back:days")]])

    wd = d.weekday()
    slots = TODAY_SLOTS if d == today else (SLOTS_BY_DATE.get(d.isoformat()) or SLOTS_BY_WD.get(wd, []))

    buttons = [[InlineKeyboardButton(s, callback_data=f"time:{date_iso}:{s}")] for s in slots]
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back:days")])
    return InlineKeyboardMarkup(buttons)

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, user: str, day: str, time_str: str):
    if not ADMIN_CHAT_ID_INT:
        return
    text = ADMIN_NOTIFY_TEXT.format(user=user, day=day, time=time_str)
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID_INT, text=text)

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text(QUESTION_TEXT)

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = (update.message.text or "").strip().lower()
    if user_text != "тяфк":
        await update.message.reply_text(WRONG_ANSWER_TEXT)
        return

    context.user_data["ok"] = True
    await update.message.reply_text(AFTER_OK_TEXT, reply_markup=build_main_keyboard())

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    data = q.data or ""

    if data == "noop":
        return

    if data == "back:main":
        await q.edit_message_text(AFTER_OK_TEXT, reply_markup=build_main_keyboard())
        return

    if data == "back:days":
        await q.edit_message_text(AFTER_RANDOM_TEXT, reply_markup=build_days_keyboard())
        return

    if data.startswith("action:"):
        action = data.split(":", 1)[1]
        if action == "random":
            await q.edit_message_text(AFTER_RANDOM_TEXT, reply_markup=build_days_keyboard())
        else:
            await q.edit_message_text("Ок) Если захочешь — возвращайся и нажми /start")
        return

    if data.startswith("day:"):
        date_iso = data.split(":", 1)[1]
        context.user_data["picked_day"] = date_iso
        await q.edit_message_text("Выбери время:", reply_markup=build_times_keyboard(date_iso))
        return

    if data.startswith("time:"):
        _, date_iso, slot = data.split(":", 2)
        d = datetime.strptime(date_iso, "%Y-%m-%d").date()

        user = q.from_user
        user_label = user.full_name
        if user.username:
            user_label += f" (@{user.username})"

        await notify_admin(context, user_label, fmt_day(d), slot)
        await q.edit_message_text(CONFIRM_TEXT)
        return

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Нажми /start чтобы начать заново.")

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty. Set it in environment variables.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
