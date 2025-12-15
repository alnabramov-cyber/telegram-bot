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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0").strip() or "0")

# ===== TZ / LOCALE =====
TZ = ZoneInfo("Europe/Minsk")
WD_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# ===== STORAGE (in-memory) =====
# date_iso -> (start_min, end_min)
ADMIN_SLOTS: dict[str, tuple[int, int]] = {}
# user_id -> {date_iso -> (start_min, end_min)}
USER_SLOTS: dict[int, dict[str, tuple[int, int]]] = {}

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
AFT
