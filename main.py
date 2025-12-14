import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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
PORT = int(os.environ.get("PORT", "10000").strip() or "10000")

# ===== TEXTS =====
QUESTION_TEXT = (
    "Привет! Раз ты здесь, значит ты посмеялась или улыбнулась, "
    "но чтобы убедиться, что ты попала сюда не просто так, ответь на вопрос:\n\n"
    "как зовут собаку, которая сначала молчит и кажется милой, "
    "а потом начинает тянуть как танк?"
)

AFTER_OK_TEXT = (
    "Привет, Полина)\n\n"
    "Я очень рад) Чтобы продолжить — выбери один из вариантов."
    # <- если хочешь, вставь сюда свой оригинальный текст
)

AFTER_RANDOM_TEXT = "Ты явно нажала случайно, поэтому выбери заново."
AFTER_YES_TEXT = "Прекрасно, я очень рад)\nВыбери день:"

FINAL_TEXT = (
    "Чудесно, жду тебя в это время по адресу:\n"
    "Дорошевича 4, подъезд 3, этаж 3, квартира 49."
)

ACCEPTED_ANSWERS = {"пуф", "пуфф"}
MAX_TRIES = 2

# ===== STATES =====
WAIT_ANSWER, CHOICE, PICK_DAY, PICK_TIME = range(4)

# ===== HEALTHCHECK FOR RENDER =====
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")


def run_http():
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


# ===== KEYBOARDS =====
def choice_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Я тоже этого хочу", callback_data="choice:yes")],
            [InlineKeyboardButton("Теоретическая кнопка", callback_data="choice:random")],
        ]
    )


def day_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Сегодня", callback_data="day:today"),
                InlineKeyboardButton("Чт", callback_data="day:thu"),
                InlineKeyboardButton("Пт", callback_data="day:fri"),
            ],
            [
                InlineKeyboardButton("Сб", callback_data="day:sat"),
                InlineKeyboardButton("Вс", callback_data="day:sun"),
            ],
        ]
    )


def time_keyboard(day: str):
    slots = {
        "today": ["После концерта"],
        "thu": ["После 19:00"],
        "fri": ["После 20:00"],
        "sat": ["После 13:00"],
        "sun": ["После 13:00"],
    }.get(day, [])

    buttons = [[InlineKeyboardButton(s, callback_data=f"time:{day}:{s}")] for s in slots]
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

    _, day = q.data.split(":")
    context.user_data["day"] = day

    await q.edit_message_text("Выбери время:", reply_markup=time_keyboard(day))
    return PICK_TIME


async def on_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "back:days":
        await q.edit_message_text(AFTER_YES_TEXT, reply_markup=day_keyboard())
        return PICK_DAY

    _, day, slot = q.data.split(":", 2)

    await q.edit_message_text(FINAL_TEXT)

    # notify admin
    if ADMIN_ID:
        user = q.from_user
        name = f"@{user.username}" if user.username else user.full_name
        msg = (
            "Новая заявка:\n"
            f"Пользователь: {name}\n"
            f"День: {day}\n"
            f"Время: {slot}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
        except Exception:
            pass

    return ConversationHandler.END


# ===== IMPORTANT: remove webhook on startup =====
async def post_init(app: Application):
    await app.bot.delete_webhook(drop_pending_updates=True)


# ===== MAIN =====
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    threading.Thread(target=run_http, daemon=True).start()

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
