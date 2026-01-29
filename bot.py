import os
import time
import db
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from dotenv import load_dotenv
from aiogram.exceptions import TelegramBadRequest


load_dotenv()

CATEGORIES = {
    "mail_combo": {
        "title": "📩 Cloud",
        "desc": "🗓️ opis",
    },
    "private_lines": {
        "title": "🔐 Priv",
        "desc": "📃 opius",
    },
    "url_cloud": {
        "title": "🔗 URL",
        "desc": "🎯 opis",
    },
    "injectables": {
        "title": "🧪 Inekcijje",
        "desc": "💎 opis",
    },
}
PRIVATE_LINE_PACKAGES = {
    "1k": {"title": "1k lines", "price_usd": 10},
    "5k": {"title": "5k lines", "price_usd": 30},
    "10k": {"title": "10k lines", "price_usd": 50},
    "30k": {"title": "30k lines", "price_usd": 100},
}
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DEPLOY_ID = os.getenv("RAILWAY_DEPLOYMENT_ID", "local")
BOT_TOKEN = os.getenv("BOT_TOKEN")
LAST_NOTICE = {}  # user_id -> message_id
LAST_SCREEN = {}  # user_id -> message_id (zadnji "menu/screen" koji treba ostati samo jedan)
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
BASE_URL = (BASE_URL or "").strip().rstrip("/")
if BASE_URL and not BASE_URL.startswith(("http://", "https://")):
    BASE_URL = "https://" + BASE_URL

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

async def delete_last_screen(chat_id: int, user_id: int):
    msg_id = LAST_SCREEN.get(user_id)
    if not msg_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass
    LAST_SCREEN.pop(user_id, None)

async def send_notice(c, text: str):
    # izbriši prethodni notice pa pošalji novi i zapamti ga
    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)
    msg = await c.message.answer(text)
    LAST_NOTICE[c.from_user.id] = msg.message_id

async def safe_edit_or_replace(c, text: str, kb: InlineKeyboardMarkup):
    """
    Pokuša editati trenutnu poruku.
    Ako ne može -> pošalje novu poruku i obriše staru, da se ne stacka.
    """
    try:
        await c.message.edit_text(text, reply_markup=kb)
        return c.message.message_id
    except TelegramBadRequest:
        msg = await c.message.answer(text, reply_markup=kb)
        # obriši staru poruku koja je trebala biti editana
        try:
            await c.message.delete()
        except Exception:
            pass
        return msg.message_id

async def send_screen(c, text: str, kb: InlineKeyboardMarkup):
    """
    Uvijek drži samo JEDAN screen message.
    Obriše stari screen, pošalje novi, zapamti ga.
    """
    await delete_last_screen(chat_id=c.message.chat.id, user_id=c.from_user.id)
    msg = await c.message.answer(text, reply_markup=kb)
    LAST_SCREEN[c.from_user.id] = msg.message_id
    return msg.message_id

async def go_home_clean(c):
    # obriši notice + screen (stare)
    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)
    await delete_last_screen(chat_id=c.message.chat.id, user_id=c.from_user.id)

    # pošalji novi home screen
    text = "🏠 Main menu\n\n📞 If you need any help, feel free to contact me at @ispodradara106\n\n⬇️ Choose the service you need down below:"
    kb = main_menu_kb()
    msg = await c.message.answer(text, reply_markup=kb)
    LAST_SCREEN[c.from_user.id] = msg.message_id

    # obriši poruku s koje je user kliknuo (invoice/status/grant itd.)
    try:
        await c.message.delete()
    except Exception:
        pass

    await c.answer()

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Mejlovi Cloud 📩", callback_data="cat:mail_combo")],
        [InlineKeyboardButton(text="🔐 FPV 🔐", callback_data="cat:private_lines")],
        [InlineKeyboardButton(text="🔗 URL 🔗", callback_data="cat:url_cloud")],
        [InlineKeyboardButton(text="🧪 Inekcije 🧪", callback_data="cat:injectables")],
    ])

def status_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Back to menu", callback_data="nav:home")],
    ])

def coin_choice_kb(cat_key: str, days: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₿ Pay with BTC", callback_data=f"pay:btc:{cat_key}:{days}")],
        [InlineKeyboardButton(text="Ł Pay with LTC", callback_data=f"pay:ltc:{cat_key}:{days}")],
        [InlineKeyboardButton(text="Ξ Pay with ETH", callback_data=f"pay:eth:{cat_key}:{days}")],
        [InlineKeyboardButton(text="💵 Pay with USDT (TRC20)", callback_data=f"pay:usdttrc20:{cat_key}:{days}")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data=f"cat:{cat_key}"),
            InlineKeyboardButton(text="🏠 Home", callback_data="nav:home"),
        ],
    ])

def private_lines_coin_kb(package_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₿ Pay with BTC", callback_data=f"plcoin:btc:{package_code}")],
        [InlineKeyboardButton(text="Ł Pay with LTC", callback_data=f"plcoin:ltc:{package_code}")],
        [InlineKeyboardButton(text="Ξ Pay with ETH", callback_data=f"plcoin:eth:{package_code}")],
        [InlineKeyboardButton(text="💵 Pay with USDT (TRC20)", callback_data=f"plcoin:usdttrc20:{package_code}")],
        [
            InlineKeyboardButton(text="🔙 Back", callback_data="cat:private_lines"),
            InlineKeyboardButton(text="🏠 Home", callback_data="nav:home"),
        ],
    ])


def category_menu_kb(cat_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Access", callback_data=f"access:{cat_key}")],
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

def category_title(cat_key: str) -> str:
    cat = CATEGORIES.get(cat_key)
    return cat["title"] if cat else cat_key

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer(
        f"👋 Welcome to ItsPeak shop!\n\n⚙️ Deploy: {DEPLOY_ID}\n\n"
        "📞 If you need any help, feel free to contact me at @ispodradara106\n\n"
        "⬇️ Choose category:",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data.startswith("cat:"))
async def open_category(c):
    cat_key = c.data.split(":", 1)[1]
    cat = CATEGORIES.get(cat_key)
    if not cat:
        await c.answer("Unknown category.")
        return

    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)

    text = f"{cat['title']}\n\n{cat['desc']}\n\n✨ Choose plan:"
    kb = kb_for_category(cat_key)

    mid = await safe_edit_or_replace(c, text, kb)
    LAST_SCREEN[c.from_user.id] = mid
    await c.answer()


@dp.callback_query(F.data == "nav:home")
async def nav_home(c):
    await go_home_clean(c)


@dp.callback_query(F.data.startswith("plan:"))
async def plan_selected(c):
    _, cat_key, days_str = c.data.split(":")
    days = int(days_str)

    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)

    text2 = (
        f"|🔴REC | You selected **{days} days** for {category_title(cat_key)}.\n\n"
        "Choose crypto to pay:"
    )
    await send_screen(c, text2, coin_choice_kb(cat_key, days))
    await c.answer()

@dp.callback_query(F.data.startswith("pl:"))
async def private_lines_selected(c):
    package = c.data.split(":", 1)[1]
    info = PRIVATE_LINE_PACKAGES.get(package)

    if not info:
        await c.answer("Unknown package.")
        return

    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)

    text = (
        f"✅ You selected **{info['title']}** — **${info['price_usd']}**\n\n"
        "Choose crypto to pay:"
    )
    await send_screen(c, text, private_lines_coin_kb(package))
    await c.answer()

@dp.callback_query(F.data == "nav:back")
async def nav_back(c):
    await go_home_clean(c)

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
    # samo admin
    if m.from_user.id != ADMIN_ID:
        try:
            await bot.delete_message(chat_id=m.chat.id, message_id=m.message_id)
        except Exception:
            pass
        return

    # obriši userovu /grant poruku
    try:
        await bot.delete_message(chat_id=m.chat.id, message_id=m.message_id)
    except Exception:
        pass

    # logika granta
    now = int(time.time())
    expires_at = now + 30 * 24 * 60 * 60
    await db.set_subscription(m.from_user.id, expires_at)

    # obriši prethodni notice (ako postoji)
    await delete_last_notice(chat_id=m.chat.id, user_id=m.from_user.id)

    # pošalji grant poruku kao notice + back button
    msg = await m.answer(
        "✅ Access successfully activated for **30 days**.",
        reply_markup=status_back_kb()
    )
    LAST_NOTICE[m.from_user.id] = msg.message_id

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
        f"{CATEGORIES[cat_key]['title']}\n\n{CATEGORIES[cat_key]['desc']}\n\n✨ Choose plan:",
        reply_markup=kb_for_category(cat_key)
    )
    await c.answer()


@dp.callback_query(F.data.startswith("pay:"))
async def pay_nowpayments(c):
    # pay:btc:mail_combo:30
    _, coin, cat_key, days_str = c.data.split(":")
    days = int(days_str)

    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/pay/nowpayments/create",
            params={
                "user_id": c.from_user.id,
                "days": days,
                "pay_currency": coin,
            },
        ) as r:
            if r.status != 200:
                txt = await r.text()
                msg = await c.message.answer(f"❌ Payment error:\n{txt}", reply_markup=status_back_kb())
                LAST_NOTICE[c.from_user.id] = msg.message_id
                await c.answer()
                return

            data = await r.json()

    invoice_url = data.get("invoice_url")
    if not invoice_url:
        msg = await c.message.answer("❌ Could not create invoice. Try again.", reply_markup=status_back_kb())
        LAST_NOTICE[c.from_user.id] = msg.message_id
        await c.answer()
        return

    cat_title = category_title(cat_key)

    msg = await c.message.answer(
        f"💳 Pay here:\n{invoice_url}\n\n"
        f"📦 Category: {cat_title}\n"
        f"⏱ Selected plan: {days} days\n\n"
        "✅ Access will be activated automatically after confirmation.",
        reply_markup=status_back_kb()
    )
    LAST_NOTICE[c.from_user.id] = msg.message_id
    await c.answer()

async def main():
    await db.init_db()
    print("✅ BOT STARTED ON RAILWAY")
    await dp.start_polling(bot)

@dp.callback_query(F.data.startswith("plcoin:"))
async def pay_private_lines_nowpayments(c):
    # plcoin:btc:1k
    _, coin, package = c.data.split(":")
    info = PRIVATE_LINE_PACKAGES.get(package)

    if not info:
        await c.answer("Unknown package.")
        return

    await delete_last_notice(chat_id=c.message.chat.id, user_id=c.from_user.id)

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/pay/nowpayments/create",
            params={
                "user_id": c.from_user.id,
                "package": package,
                "pay_currency": coin,
                "kind": "private_lines",
            },
        ) as r:
            if r.status != 200:
                txt = await r.text()
                msg = await c.message.answer(f"❌ Payment error:\n{txt}", reply_markup=status_back_kb())
                LAST_NOTICE[c.from_user.id] = msg.message_id
                await c.answer()
                return

            data = await r.json()

    invoice_url = data.get("invoice_url")
    if not invoice_url:
        msg = await c.message.answer("❌ Could not create invoice. Try again.", reply_markup=status_back_kb())
        LAST_NOTICE[c.from_user.id] = msg.message_id
        await c.answer()
        return

    msg = await c.message.answer(
        f"💳 Pay here:\n{invoice_url}\n\n"
        f"📦 Category: {category_title('private_lines')}\n"
        f"📦 Package: {info['title']} — ${info['price_usd']}\n\n"
        "✅ Delivery will be sent automatically after confirmation.",
        reply_markup=status_back_kb()
    )
    LAST_NOTICE[c.from_user.id] = msg.message_id
    await c.answer()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
