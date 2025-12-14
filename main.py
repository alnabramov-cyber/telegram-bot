import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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
    ConversationHandler,
    filters,
)

# ====== ENV ======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0").strip() or "0")
PORT = int(os.environ.get("PORT", "10000"))

# Тексты (можешь менять)
QUESTION_TEXT = (
    "Привет! Раз ты здесь, значит ты посмеялась или улыбнулась, но чтобы убедиться, "
    "что ты попала сюда не просто так, ответь на вопрос: как зовут собаку, которая сначала "
    "молчит и кажется милой, а потом начинает тянуть как танк?"
)
AFTER_OK_TEXT = (
    "Привет, Полина)\n\n"
    "Я хочу тебя касаться, доставлять тебе удовольствие и заняться с тобой сексом. "
    "Это прекрасно, не так ли?) Чтобы это произошло выбери один из вариантов."
)
AFTER_YES_TEXT = "Прекрасно, я очень рад)\nВыбери день:"
AFTER_RANDOM_TEXT = "Ты явно нажала случайно, поэтому выбери заново."
FINAL_TEXT = (
    "Чудесно, жду тебя в это время по адресу Дорошевича 4, подъезд 3, этаж 3, квартира 49."
)

ACCEPTED_ANSWERS = {"пуф", "пуфф"}  # регистр не важен
MAX_TRIES = 2

# ====== Storage (простое: в памяти) ======
# schedule: {"mon": ["21:00-23:30", ...], ...}
schedule = {
    "mon": [],
    "tue": [],
    "wed": [],
    "thu": [],
    "fri": [],
    "sat": [],
    "sun": [],
}

DAY_LABELS = {
    "mon": "Пн",
    "tue": "Вт",
    "wed": "Ср",
    "thu": "Чт",
    "fri": "Пт",
    "sat": "Сб",
    "sun": "Вс",
}
DAY_ALIASES = {
    # EN
    "mon": "mon", "monday": "mon",
    "tue": "tue", "tuesday": "tue",
    "wed": "wed", "wednesday": "wed",
    "thu": "thu", "thursday": "thu",
    "fri": "fri", "friday": "fri",
    "sat": "sat", "saturday": "sat",
    "sun": "sun", "sunday": "sun",
    # RU
    "пн": "mon", "понедельник": "mon",
    "вт": "tue", "вторник": "tue",
    "ср": "wed", "среда": "wed",
    "чт": "thu", "четверг": "thu",
    "пт": "fri", "пятница": "fri",
    "сб": "sat", "суббота": "sat",
    "вс": "sun", "воскресенье": "sun",
}

TIME_RE = re.compile(r"^\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*$")

# ====== Conversation states ======
WAIT_ANSWER, CHOICE, PICK_DAY, PICK_TIME = range(4)

# ====== Render healthcheck HTTP ======
class Handler(BaseHTTPRequestHandler):
    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self._ok()

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_http():
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


def is_admin(user_id: int) -> bool:
    return ADMIN_ID and user_id == ADMIN_ID


def normalize_answer(text: str) -> str:
    return (text or "").strip().lower()


def normalize_day(day_raw: str) -> str | None:
    key = (day_raw or "").strip().lower()
    return DAY_ALIASES.get(key)


def available_days():
    return [d for d, slots in schedule.items() if slots]


def day_keyboard():
    days = available_days()
    if not days:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Нет доступных дней", callback_data="noop")]])
    rows = []
    row = []
    for d in days:
        row.append(InlineKeyboardButton(DAY_LABELS[d], callback_data=f"day:{d}"))
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def time_keyboard(day: str):
    slots = schedule.get(day, [])
    rows = [[InlineKeyboardButton(s, callback_data=f"time:{day}:{s}")] for s in slots]
    rows.append([InlineKeyboardButton("⬅️ Назад к дням", callback_data="back:days")])
    return InlineKeyboardMarkup(rows)


def choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Я тоже этого хочу", callback_data="choice:yes")],
        [InlineKeyboardButton("Теоретическая кнопка", callback_data="choice:random")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tries"] = 0
    context.user_data.pop("verified", None)
    await update.message.reply_text(QUESTION_TEXT)
    return WAIT_ANSWER


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = normalize_answer(update.message.text)
    tries = int(context.user_data.get("tries", 0)) + 1
    context.user_data["tries"] = tries

    if ans in ACCEPTED_ANSWERS:
        context.user_data["verified"] = True
        await update.message.reply_text(AFTER_OK_TEXT, reply_markup=choice_keyboard())
        return CHOICE

    if tries >= MAX_TRIES:
        await update.message.reply_text("Неверно. Доступ закрыт.")
        return ConversationHandler.END

    await update.message.reply_text("Неверно. Попробуй еще раз:")
    return WAIT_ANSWER


async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    data = q.data
    if data == "choice:random":
        await q.edit_message_text(AFTER_RANDOM_TEXT, reply_markup=choice_keyboard())
        return CHOICE

    if data == "choice:yes":
        await q.edit_message_text(AFTER_YES_TEXT, reply_markup=day_keyboard())
        return PICK_DAY

    return CHOICE


async def on_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "noop":
        return PICK_DAY

    _, day = q.data.split(":", 1)
    context.user_data["picked_day"] = day
    await q.edit_message_text(f"Выбери время на {DAY_LABELS[day]}:", reply_markup=time_keyboard(day))
    return PICK_TIME


async def on_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "back:days":
        await q.edit_message_text(AFTER_YES_TEXT, reply_markup=day_keyboard())
        return PICK_DAY

    # time:<day>:<slot>
    _, day, slot = q.data.split(":", 2)
    user = q.from_user
    username = user.username or ""
    name = user.full_name or ""

    await q.edit_message_text(FINAL_TEXT)

    # notify admin
    if ADMIN_ID:
        msg = (
            "Новая заявка:\n"
            f"Юзер: @{username}" if username else f"Юзер: {name}"
        )
        msg += f"\nДень: {DAY_LABELS.get(day, day)}\nВремя: {slot}"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
        except Exception:
            pass

    return ConversationHandler.END


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    # /set_time <day> <HH:MM-HH:MM>
    if len(context.args) < 2:
        await update.message.reply_text("Формат: /set_time <день> <21:00-23:30>")
        return

    day = normalize_day(context.args[0])
    slot = " ".join(context.args[1:]).strip()

    if not day:
        await update.message.reply_text("Не понял день. Пример: /set_time пн 21:00-23:30")
        return
    if not TIME_RE.match(slot):
        await update.message.reply_text("Не понял время. Пример: 21:00-23:30")
        return

    schedule.setdefault(day, [])
    if slot not in schedule[day]:
        schedule[day].append(slot)

    await update.message.reply_text(f"Ок. {DAY_LABELS[day]}: добавил {slot}")


async def show_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    lines = []
    for d in ["mon","tue","wed","thu","fri","sat","sun"]:
        slots = schedule.get(d, [])
        if slots:
            lines.append(f"{DAY_LABELS[d]}: " + ", ".join(slots))
    await update.message.reply_text("\n".join(lines) if lines else "Пока пусто. Добавь через /set_time")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty (set Render env var BOT_TOKEN)")

    threading.Thread(target=run_http, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, answer)],
            CHOICE: [CallbackQueryHandler(on_choice, pattern=r"^choice:")],
            PICK_DAY: [CallbackQueryHandler(on_day, pattern=r"^(day:|noop$)")],
            PICK_TIME: [CallbackQueryHandler(on_time, pattern=r"^(time:|back:)")],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("set_time", set_time))
    app.add_handler(CommandHandler("show_time", show_time))

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
