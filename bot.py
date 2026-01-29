import os
import time
import db
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()

CATEGORIES = {
    "mail_combo": {
        "title": "📩 Mail Combo Cloud",
        "desc": "🗓️ You get shared hotmail/gmail/mixed lines DAILY.",
    },
    "private_lines": {
        "title": "🔐 Full Private Lines",
        "desc": "📃 You get 1:1 private untouched lines.",
    },
    "url_cloud": {
        "title": "🔗 URL Cloud",
        "desc": "🎯 You get URL cloud for making combos, ready for SQLI testing.",
    },
    "injectables": {
        "title": "🧪 Injectables Cloud",
        "desc": "💎 You get a private injectables ready for data dumping (names, numbers, email, passwords, etc.).",
    },
}
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
LAST_NOTICE = {}  # user_id -> message_id
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def delete_last_notice(chat_id: int, user_id: int):
    msg_id = LAST_NOTICE.get(user_id)
    if not msg_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass
    LAST_NOTICE.pop(user_id, None)

async def send_notice(c, text: str):
    # izbriši prethodni notice pa pošalji novi i zapamti ga
    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)
    msg = await c.message.answer(text)
    LAST_NOTICE[c.from_user.id] = msg.message_id

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Mail Combo Cloud 📩", callback_data="cat:mail_combo")],
        [InlineKeyboardButton(text="🔐 Full Private Lines 🔐", callback_data="cat:private_lines")],
        [InlineKeyboardButton(text="🔗 URL Cloud 🔗", callback_data="cat:url_cloud")],
        [InlineKeyboardButton(text="🧪 Injectables Cloud 🧪", callback_data="cat:injectables")],
    ])

def status_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Back to menu", callback_data="nav:home")],
    ])

def category_menu_kb(cat_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Pristup", callback_data=f"access:{cat_key}")],
        [InlineKeyboardButton(text="💳 Kupi 30 dana (uskoro)", callback_data=f"buy:{cat_key}")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Home", callback_data="nav:home"),
        ],
    ])

def mail_combo_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10 DAY ACCESS", callback_data="plan:mail_combo:10")],
        [InlineKeyboardButton(text="30 DAY ACCESS", callback_data="plan:mail_combo:30")],
        [InlineKeyboardButton(text="90 DAY ACCESS", callback_data="plan:mail_combo:90")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Home", callback_data="nav:home"),
        ],
    ])

def private_lines_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1K LINES - $10", callback_data="pl:1k")],
        [InlineKeyboardButton(text="5K LINES - $30", callback_data="pl:5k")],
        [InlineKeyboardButton(text="10K LINES - $50", callback_data="pl:10k")],
        [InlineKeyboardButton(text="30K LINES - $100", callback_data="pl:30k")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Home", callback_data="nav:home"),
        ],
    ])

def url_cloud_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10 DAY ACCESS", callback_data="plan:url_cloud:10")],
        [InlineKeyboardButton(text="30 DAY ACCESS", callback_data="plan:url_cloud:30")],
        [InlineKeyboardButton(text="90 DAY ACCESS", callback_data="plan:url_cloud:90")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Home", callback_data="nav:home"),
        ],
    ])

def injectables_cloud_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10 DAY ACCESS", callback_data="plan:injectables:10")],
        [InlineKeyboardButton(text="30 DAY ACCESS", callback_data="plan:injectables:30")],
        [InlineKeyboardButton(text="90 DAY ACCESS", callback_data="plan:injectables:90")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="nav:back"),
            InlineKeyboardButton(text="🏠 Home", callback_data="nav:home"),
        ],
    ])

def kb_for_category(cat_key: str) -> InlineKeyboardMarkup:
    if cat_key == "mail_combo":
        return mail_combo_plans_kb()
    if cat_key == "private_lines":
        return private_lines_plans_kb()
    if cat_key == "url_cloud":
        return url_cloud_plans_kb()
    if cat_key == "injectables":
        return injectables_cloud_plans_kb()
    return category_menu_kb(cat_key)

def safe_cat_key_from_pl(code: str) -> str:
    # private lines callback nema cat_key pa ga fiksno vraćamo
    return "private_lines"

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer(
        "👋 Welcome to ItsPeak shop!\n\n📞 If you need any help, feel free to contact me at @ispodradara106\n\n⬇️ Choose category:",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data.startswith("cat:"))
async def open_category(c):
    cat_key = c.data.split(":", 1)[1]
    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)
    cat = CATEGORIES.get(cat_key)
    if not cat:
        await c.answer("Nepoznata kategorija.")
        return

    text = f"{cat['title']}\n\n{cat['desc']}\n\n✨ Choose plan:"

    if cat_key == "mail_combo":
        await c.message.edit_text(text, reply_markup=mail_combo_plans_kb())
    elif cat_key == "private_lines":
        await c.message.edit_text(text, reply_markup=private_lines_plans_kb())
    elif cat_key == "url_cloud":
        await c.message.edit_text(text, reply_markup=url_cloud_plans_kb())
    elif cat_key == "injectables":
        await c.message.edit_text(text, reply_markup=injectables_cloud_plans_kb())
    else:
        await c.message.edit_text(text, reply_markup=category_menu_kb(cat_key))


    await c.answer()


@dp.callback_query(F.data == "nav:home")
async def nav_home(c):
    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)

    await c.message.edit_text(
        "🏠 Main menu\n\n📞 If you need any help, feel free to contact me at @ispodradara106\n\n⬇️ Choose the service you need down below:",
        reply_markup=main_menu_kb()
    )
    await c.answer()

@dp.callback_query(F.data.startswith("plan:"))
async def plan_selected(c):
    _, cat_key, days_str = c.data.split(":")
    days = int(days_str)

    # ostavi UI poruku (menu) kako je – može ostati edit ili ne
    # ovdje ne diramo menu, samo šaljemo notice ispod
    await send_notice(
        c,
        f"| 🔴REC | You have chosen {days} DAY ACCESS for {CATEGORIES[cat_key]['title']}.\n\n"
        "🔗 tu ce biti cloud."
    )
    await c.answer()

@dp.callback_query(F.data.startswith("pl:"))
async def private_lines_selected(c):
    code = c.data.split(":", 1)[1]

    mapping = {
        "1k": "1k lines - $10",
        "5k": "5k lines - $30",
        "10k": "10k lines - $50",
        "30k": "30k lines - $100",
    }
    picked = mapping.get(code, "Selected package")

    await send_notice(
        c,
        f"| 🔴REC | You have chosen: {picked}\n\n"
        "🔗 tu ce biti link za kupnju."
    )
    await c.answer()

@dp.callback_query(F.data == "nav:back")
async def nav_back(c):
    # za sada back = home
    await nav_home(c)

@dp.message(Command("status"))
async def status(m: Message):
    # 1) obriši userovu /status poruku (u privatnom chatu radi)
    try:
        await bot.delete_message(chat_id=m.chat.id, message_id=m.message_id)
    except Exception:
        pass

    now = int(time.time())
    exp = await db.get_subscription_expires_at(m.from_user.id)

    if exp > now:
        text = f"✅ Access active until: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp))}"
    else:
        text = "❌ No active access."

    # 2) pošalji status poruku kao "notice" (da se može brisati)
    # koristimo tvoj LAST_NOTICE sistem
    # fake callback object nemamo, pa ručno: obriši prethodni notice pa pošalji novi
    await delete_last_notice(chat_id=m.chat.id, user_id=m.from_user.id)
    msg = await m.answer(text, reply_markup=status_back_kb())
    LAST_NOTICE[m.from_user.id] = msg.message_id

# Admin komanda (za početak): ručno aktivira 30 dana
# Napomena: ovo je MVP. Kasnije ograničimo na tvoj user_id.
@dp.message(Command("grant"))
async def grant(m: Message):
    if m.from_user.id != ADMIN_ID:
        await m.answer("⛔ Nemaš ovlaštenje za ovu komandu.")
        return

    now = int(time.time())
    expires_at = now + 30 * 24 * 60 * 60
    await db.set_subscription(m.from_user.id, expires_at)
    await m.answer("✅ Aktivirao sam pristup na 30 dana (SQLite).")

@dp.callback_query(F.data.startswith("access:"))
async def access_callback(c):
    cat_key = c.data.split(":", 1)[1]

    user_id = c.from_user.id
    now = int(time.time())
    exp = await db.get_subscription_expires_at(user_id)

    if exp <= now:
        await c.message.answer("❌ Nemaš aktivan pristup. Klikni “Kupi 30 dana”.")
        await c.answer()
        return

    token = await db.create_token(user_id, ttl_seconds=600)
    link = f"{BASE_URL}/access?token={token}"
    await c.message.answer(
        f"✅ Pristup odobren za: {CATEGORIES[cat_key]['title']}\n\n"
        f"Privremeni link (10 min):\n{link}"
    )
    await c.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def buy_callback(c):
    cat_key = c.data.split(":", 1)[1]
    await c.message.edit_text(
        f"💳 Purchase for {CATEGORIES[cat_key]['title']} coming soon.",
        reply_markup=kb_for_category(cat_key)
    )
    await c.answer()

async def main():
    await db.init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
