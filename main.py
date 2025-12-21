import os
import json
import re
from pathlib import Path
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

# ===== TIMEZONE =====
TZ = ZoneInfo("Europe/Minsk")  # GMT+3
WD_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# ===== STORAGE =====
STORAGE_PATH = Path("storage.json")

def load_storage() -> dict:
    if not STORAGE_PATH.exists():
        return {"admin": {}, "user": {}}
    try:
        return json.loads(STORAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"admin": {}, "user": {}}

def save_storage(data: dict) -> None:
    STORAGE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def is_admin(user_id: int) -> bool:
    return bool(ADMIN_ID) and user_id == ADMIN_ID

def my_key(user_id: int) -> str:
    return "admin" if is_admin(user_id) else "user"

def other_key(user_id: int) -> str:
    return "user" if is_admin(user_id) else "admin"

# ===== TIME PARSING =====
RE_RANGE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$")
RE_AFTER = re.compile(r"^\s*после\s+(\d{1,2}:\d{2})\s*$", re.IGNORECASE)

def parse_minutes(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    h = int(hh); m = int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError
    return h * 60 + m

def fmt_minutes(m: int) -> str:
    return f"{m//60:02d}:{m%60:02d}"

def parse_interval(text: str) -> tuple[int, int]:
    m = RE_RANGE.match(text)
    if m:
        start = parse_minutes(m.group(1))
        end = parse_minutes(m.group(2))
        if end <= start:
            raise ValueError
        return start, end

    m = RE_AFTER.match(text)
    if m:
        start = parse_minutes(m.group(1))
        end = 23 * 60 + 59
        return start, end

    raise ValueError

def interval_to_str(start: int, end: int) -> str:
    return f"{fmt_minutes(start)}-{fmt_minutes(end)}"

def intersect(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int] | None:
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    if e <= s:
        return None
    return (s, e)

# ===== TEXTS =====
QUESTION_TEXT = "Введи кодовое слово, пожалуйста."
AFTER_OK_TEXT = "Привет, Полина)\nИ когда же в этот раз?"
MENU_TEXT = "Выбери действие:"
SET_TEXT = "Выбери день (только ближайшие 7 дней):"
TIME_PROMPT = (
    "Введи время для {date_label}.\n\n"
    "Формат:\n"
    "• чч:мм-чч:мм (например 18:30 - 22:00)\n"
    "• после чч:мм (например после 16:00)\n\n"
    "Пробелы возле дефиса можно."
)

YANDEX_MAPS_URL = "https://yandex.ru/maps?text=53.918795,27.588825&si=f8fwk7wvw7hmh0cac49347aqmw"
FINAL_TEXT = (
    "Чудесно, жду тебя в это время по адресу:\n"
    "Дорошевича 4, подъезд 3, этаж 3, квартира 49.\n\n"
    f"Яндекс Карты: {YANDEX_MAPS_URL}"
)

ACCEPTED_ANSWERS = {"пуф", "пуфф"}
MAX_TRIES = 2

# ===== STATES =====
WAIT_CODE, MENU, PICK_DAY, WAIT_TIME, PICK_MEET_DAY, PICK_MEET_TIME = range(6)

# ===== KEYBOARDS =====
def menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Задать мои слоты", callback_data="menu:set")],
        [InlineKeyboardButton("👀 Посмотреть слоты другой стороны", callback_data="menu:view_other")],
        [InlineKeyboardButton("🔁 Посмотреть пересечения", callback_data="menu:overlap_text")],
        [InlineKeyboardButton("📅 Выбрать время из пересечений", callback_data="menu:overlap_pick")],
    ])

def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В меню", callback_data="back:menu")]])

def days_kb_7() -> InlineKeyboardMarkup:
    today = datetime.now(TZ).date()
    buttons = []
    row = []
    for i in range(7):
        d = today + timedelta(days=i)
        label = f"{d:%d.%m} {WD_RU[d.weekday()]}"
        row.append(InlineKeyboardButton(label, callback_data=f"day:{d.isoformat()}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ В меню", callback_data="back:menu")])
    return InlineKeyboardMarkup(buttons)

def back_to_days_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад к дням", callback_data="back:days")],
        [InlineKeyboardButton("⬅️ В меню", callback_data="back:menu")],
    ])

# ===== HELPERS =====
def format_slots(slots: dict) -> str:
    if not slots:
        return "Слоты пока не заданы."
    lines = []
    for date_iso in sorted(slots.keys()):
        d = date.fromisoformat(date_iso)
        times = ", ".join(slots[date_iso])
        lines.append(f"{d:%d.%m} {WD_RU[d.weekday()]}: {times}")
    return "\n".join(lines)

def compute_overlaps(admin_slots: dict, user_slots: dict) -> dict:
    res = {}
    for date_iso in sorted(set(admin_slots.keys()) & set(user_slots.keys())):
        out = []
        for a_str in admin_slots.get(date_iso, []):
            a_int = parse_interval(a_str)
            for u_str in user_slots.get(date_iso, []):
                u_int = parse_interval(u_str)
                inter = intersect(a_int, u_int)
                if inter:
                    out.append(interval_to_str(inter[0], inter[1]))
        if out:
            res[date_iso] = sorted(set(out))
    return res

def overlaps_days_kb(overlaps: dict) -> InlineKeyboardMarkup:
    # показываем только ближайшие 7 дней
    today = datetime.now(TZ).date()
    allowed = { (today + timedelta(days=i)).isoformat() for i in range(7) }

    buttons = []
    row = []
    for date_iso in sorted(overlaps.keys()):
        if date_iso not in allowed:
            continue
        d = date.fromisoformat(date_iso)
        label = f"{d:%d.%m} {WD_RU[d.weekday()]}"
        row.append(InlineKeyboardButton(label, callback_data=f"meetday:{date_iso}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if not buttons:
        return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В меню", callback_data="back:menu")]])

    buttons.append([InlineKeyboardButton("⬅️ В меню", callback_data="back:menu")])
    return InlineKeyboardMarkup(buttons)

def overlaps_time_kb(date_iso: str, overlaps: dict) -> InlineKeyboardMarkup:
    times = overlaps.get(date_iso, [])
    buttons = [[InlineKeyboardButton(t, callback_data=f"meettm:{date_iso}:{t}")] for t in times]
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back:meetdays")])
    buttons.append([InlineKeyboardButton("⬅️ В меню", callback_data="back:menu")])
    return InlineKeyboardMarkup(buttons)

# ===== AUTH =====
def is_authed(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("authed"))

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["tries"] = 0
    context.user_data["authed"] = False
    await update.message.reply_text(QUESTION_TEXT)
    return WAIT_CODE

async def code_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    context.user_data["tries"] = int(context.user_data.get("tries", 0)) + 1

    if text in ACCEPTED_ANSWERS:
        context.user_data["authed"] = True
        await update.message.reply_text(MENU_TEXT, reply_markup=menu_kb())
        return MENU

    if context.user_data["tries"] >= MAX_TRIES:
        await update.message.reply_text("Неверно. Доступ закрыт.")
        return ConversationHandler.END

    await update.message.reply_text("Неверно. Попробуй еще раз:")
    return WAIT_CODE

async def slots_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # админ всегда может, пользователь — только после /start и правильного слова
    if not is_admin(update.effective_user.id) and not is_authed(context):
        await update.message.reply_text("Сначала /start и кодовое слово.")
        return WAIT_CODE

    await update.message.reply_text(MENU_TEXT, reply_markup=menu_kb())
    return MENU

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "back:menu":
        await q.edit_message_text(MENU_TEXT, reply_markup=menu_kb())
        return MENU

    if q.data == "menu:set":
        await q.edit_message_text(SET_TEXT, reply_markup=days_kb_7())
        return PICK_DAY

    if q.data == "menu:view_other":
        data = load_storage()
        other = data.get(other_key(q.from_user.id), {})
        if not other:
            await q.edit_message_text("Слоты второй стороны пока не заданы.", reply_markup=back_to_menu_kb())
            return MENU
        await q.edit_message_text(format_slots(other), reply_markup=back_to_menu_kb())
        return MENU

    if q.data == "menu:overlap_text":
        data = load_storage()
        admin_slots = data.get("admin", {})
        user_slots = data.get("user", {})

        # если у другой стороны нет слотов — ошибка
        if is_admin(q.from_user.id):
            if not user_slots:
                await q.edit_message_text("Слоты второй стороны пока не заданы.", reply_markup=back_to_menu_kb())
                return MENU
        else:
            if not admin_slots:
                await q.edit_message_text("Слоты второй стороны пока не заданы.", reply_markup=back_to_menu_kb())
                return MENU

        overlaps = compute_overlaps(admin_slots, user_slots)
        if not overlaps:
            await q.edit_message_text("Пересечений нет.", reply_markup=back_to_menu_kb())
            return MENU

        await q.edit_message_text(format_slots(overlaps), reply_markup=back_to_menu_kb())
        return MENU

    if q.data == "menu:overlap_pick":
        data = load_storage()
        admin_slots = data.get("admin", {})
        user_slots = data.get("user", {})

        if is_admin(q.from_user.id):
            if not user_slots:
                await q.edit_message_text("Слоты второй стороны пока не заданы.", reply_markup=back_to_menu_kb())
                return MENU
        else:
            if not admin_slots:
                await q.edit_message_text("Слоты второй стороны пока не заданы.", reply_markup=back_to_menu_kb())
                return MENU

        overlaps = compute_overlaps(admin_slots, user_slots)
        if not overlaps:
            await q.edit_message_text("Пересечений нет.", reply_markup=back_to_menu_kb())
            return MENU

        context.user_data["overlaps"] = overlaps
        await q.edit_message_text("Выбери день из пересечений (ближайшие 7 дней):", reply_markup=overlaps_days_kb(overlaps))
        return PICK_MEET_DAY

    return MENU

async def on_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "back:menu":
        await q.edit_message_text(MENU_TEXT, reply_markup=menu_kb())
        return MENU

    _, date_iso = q.data.split(":", 1)
    context.user_data["date_iso"] = date_iso

    d = date.fromisoformat(date_iso)
    date_label = f"{d:%d.%m} {WD_RU[d.weekday()]}"
    await q.edit_message_text(TIME_PROMPT.format(date_label=date_label), reply_markup=back_to_days_kb())
    return WAIT_TIME

async def on_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "back:days":
        await q.edit_message_text(SET_TEXT, reply_markup=days_kb_7())
        return PICK_DAY

    if q.data == "back:menu":
        await q.edit_message_text(MENU_TEXT, reply_markup=menu_kb())
        return MENU

    if q.data == "back:meetdays":
        overlaps = context.user_data.get("overlaps", {})
        await q.edit_message_text("Выбери день из пересечений (ближайшие 7 дней):", reply_markup=overlaps_days_kb(overlaps))
        return PICK_MEET_DAY

    return MENU

async def on_time_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_iso = context.user_data.get("date_iso")
    if not date_iso:
        await update.message.reply_text("Открой меню: /slots")
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    try:
        start_m, end_m = parse_interval(text)
    except ValueError:
        await update.message.reply_text(
            "Не понял формат.\nПримеры:\n• 18:30 - 22:00\n• после 16:00"
        )
        return WAIT_TIME

    interval_str = interval_to_str(start_m, end_m)

    data = load_storage()
    key = my_key(update.effective_user.id)
    data.setdefault(key, {})
    # перезапись слотов на выбранную дату
    data[key][date_iso] = [interval_str]
    save_storage(data)

    d = date.fromisoformat(date_iso)
    date_label = f"{d:%d.%m} {WD_RU[d.weekday()]}"
    await update.message.reply_text(f"Записал: {date_label} — {interval_str}", reply_markup=menu_kb())
    return MENU

async def on_meet_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "back:menu":
        await q.edit_message_text(MENU_TEXT, reply_markup=menu_kb())
        return MENU

    _, date_iso = q.data.split(":", 1)
    overlaps = context.user_data.get("overlaps", {})
    if not overlaps.get(date_iso):
        await q.edit_message_text("На этот день пересечений нет.", reply_markup=back_to_menu_kb())
        return MENU

    d = date.fromisoformat(date_iso)
    title = f"Выбери время ({d:%d.%m} {WD_RU[d.weekday()]})"
    await q.edit_message_text(title, reply_markup=overlaps_time_kb(date_iso, overlaps))
    return PICK_MEET_TIME

async def on_meet_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data.startswith("meettm:"):
        _, date_iso, slot = q.data.split(":", 2)

        # финальное сообщение пользователю
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

    return PICK_MEET_TIME

# ===== MAIN =====
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("slots", slots_cmd),
        ],
        states={
            WAIT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_answer)],
            MENU: [
                CallbackQueryHandler(on_back, pattern=r"^back:menu$"),
                CallbackQueryHandler(on_menu, pattern=r"^(menu:|back:menu)"),
            ],
            PICK_DAY: [
                CallbackQueryHandler(on_back, pattern=r"^back:(menu|days)$"),
                CallbackQueryHandler(on_day, pattern=r"^day:"),
            ],
            WAIT_TIME: [
                CallbackQueryHandler(on_back, pattern=r"^back:(menu|days)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_time_text),
            ],
            PICK_MEET_DAY: [
                CallbackQueryHandler(on_back, pattern=r"^back:(menu|meetdays)$"),
                CallbackQueryHandler(on_meet_day, pattern=r"^meetday:"),
            ],
            PICK_MEET_TIME: [
                CallbackQueryHandler(on_back, pattern=r"^back:(menu|meetdays)$"),
                CallbackQueryHandler(on_meet_time, pattern=r"^meettm:"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("slots", slots_cmd),
        ],
    )

    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
