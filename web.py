import time
import os
import hmac
import hashlib
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv
from typing import Optional

import db

load_dotenv()

app = FastAPI()

DRIVE_LINKS = {
    "mail_combo": "https://drive.google.com/drive/folders/XXXXX_MAIL",
    "url_cloud": "https://drive.google.com/drive/folders/XXXXX_URL",
    "injectables": "https://mega.nz/folder/no4CDKzC#ulHfTi9G3khXSmndbVT6qA",
}
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")  # isti token kao u bot.py
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")

async def tg_send_message(chat_id: int, text: str, reply_markup: dict | None = None):
    """
    Pošalje Telegram poruku useru direktno preko Bot API.
    reply_markup: dict (InlineKeyboardMarkup) ili None
    """
    if not BOT_TOKEN:
        print("BOT_TOKEN missing - cannot send Telegram message")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
        if r.status_code != 200:
            print("Telegram sendMessage failed:", r.status_code, r.text)
    except Exception as e:
        print("Telegram sendMessage exception:", repr(e))

def back_to_menu_kb() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🏠 Back to menu", "url": f"https://t.me/{BOT_USERNAME}?start=1"}]
        ]
    }

@app.on_event("startup")
async def on_startup():
    await db.init_db()


@app.get("/access")
async def access(token: str, cat: str):
    now = int(time.time())

    data = await db.get_token(token)
    if not data:
        raise HTTPException(status_code=403, detail="Invalid token")

    if data["expires_at"] < now:
        await db.delete_token(token)
        raise HTTPException(status_code=403, detail="Token expired")

    user_id = data["user_id"]
    sub_exp = await db.get_subscription_expires_at(user_id, sub_type=cat)

    if sub_exp < now:
        raise HTTPException(status_code=403, detail="No active access")

    drive_link = DRIVE_LINKS.get(cat)
    if not drive_link:
        raise HTTPException(status_code=400, detail="Unknown category")

    token_exp = int(data["expires_at"])

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Cloud Access</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .card {{
                background: #ffffff;
                border-radius: 20px;
                padding: 36px 40px;
                max-width: 560px;
                width: calc(100% - 32px);
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
                text-align: center;
            }}

            .badge {{
                display: inline-block;
                padding: 6px 14px;
                border-radius: 999px;
                background: #eef2ff;
                color: #3730a3;
                font-size: 14px;
                font-weight: 700;
                margin-bottom: 18px;
            }}

            h2 {{
                margin: 0 0 10px 0;
                color: #111827;
            }}

            .button {{
                display: inline-block;
                padding: 16px 36px;
                background: linear-gradient(135deg, #1a73e8, #0b5ed7);
                color: #ffffff;
                text-decoration: none;
                border-radius: 999px;
                font-size: 17px;
                font-weight: 800;
                box-shadow: 0 10px 25px rgba(26, 115, 232, 0.45);
                transition: transform 0.15s ease, box-shadow 0.15s ease;
            }}

            .button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 14px 32px rgba(26, 115, 232, 0.6);
            }}

            .timers {{
                margin-top: 18px;
                display: flex;
                flex-direction: column;
                gap: 10px;
                align-items: center;
            }}

            .pill {{
                padding: 10px 16px;
                border-radius: 14px;
                background: #f3f4f6;
                color: #111827;
                font-size: 14px;
                font-weight: 750;
                display: inline-block;
                min-width: 260px;
                text-align: center;
            }}

            .pill small {{
                display: block;
                margin-top: 4px;
                font-size: 12px;
                color: #6b7280;
                font-weight: 600;
            }}

            .expired {{
                margin-top: 18px;
                padding: 12px 14px;
                border-radius: 12px;
                background: #fee2e2;
                color: #991b1b;
                font-size: 14px;
                font-weight: 800;
                display: none;
            }}

            .footer {{
                margin-top: 26px;
                font-size: 13px;
                color: #6b7280;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="badge">🔐 Category: {cat}</div>

            <h2>✅ Access granted</h2>

            <a href="{drive_link}" target="_blank" class="button" id="openBtn">
                🔗 Open Cloud
            </a>

            <div class="timers">
                <div class="pill">
                    ⏳ Link expires in <span id="tokenTimer">--:--</span>
                    <small>Temporary link (token expiry)</small>
                </div>

                <div class="pill">
                    🧾 Subscription expires in <span id="subTimer">--</span>
                    <small>Countdown until your subscription ends</small>
                </div>
            </div>

            <div class="expired" id="expiredBox">
                ⚠️ This access link has expired. Please generate a new one from the bot.
            </div>

            <div class="footer">
                Secure access · Temporary link · Do not share
            </div>
        </div>

        <script>
            const tokenExpMs = {int(token_exp)} * 1000;
            const subExpMs   = {int(sub_exp)} * 1000;

            const tokenTimerEl = document.getElementById("tokenTimer");
            const subTimerEl   = document.getElementById("subTimer");
            const expiredBox   = document.getElementById("expiredBox");
            const openBtn      = document.getElementById("openBtn");

            function pad(n) {{
                return String(n).padStart(2, "0");
            }}

            function formatDHMS(totalSeconds) {{
                // returns "Xd Yh Zm" (or "Ym Zs" if short)
                let s = Math.max(0, totalSeconds);

                const days = Math.floor(s / 86400);
                s %= 86400;
                const hours = Math.floor(s / 3600);
                s %= 3600;
                const mins = Math.floor(s / 60);
                const secs = s % 60;

                if (days > 0) return `${{days}}d ${{hours}}h ${{mins}}m`;
                if (hours > 0) return `${{hours}}h ${{mins}}m ${{secs}}s`;
                if (mins > 0) return `${{mins}}m ${{secs}}s`;
                return `${{secs}}s`;
            }}

            function tick() {{
                const now = Date.now();

                // --- TOKEN countdown (mm:ss) ---
                let tokenDiff = Math.floor((tokenExpMs - now) / 1000);
                if (tokenDiff <= 0) {{
                    tokenTimerEl.textContent = "00:00";
                    expiredBox.style.display = "block";
                    openBtn.style.pointerEvents = "none";
                    openBtn.style.opacity = "0.5";
                    openBtn.textContent = "🔒 Link Expired";
                }} else {{
                    const m = Math.floor(tokenDiff / 60);
                    const s = tokenDiff % 60;
                    tokenTimerEl.textContent = `${{pad(m)}}:${{pad(s)}}`;
                }}

                // --- SUBSCRIPTION countdown (d/h/m/s) ---
                let subDiff = Math.floor((subExpMs - now) / 1000);
                if (subDiff <= 0) {{
                    subTimerEl.textContent = "Expired";
                }} else {{
                    subTimerEl.textContent = formatDHMS(subDiff);
                }}
            }}

            tick();
            setInterval(tick, 1000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(html)

@app.post("/pay/nowpayments/create")
async def create_nowpayments_invoice(
    user_id: int,
    pay_currency: str,
    days: Optional[int] = None,
    kind: str = "subscription",
    package: Optional[str] = None,
    cat_key: Optional[str] = None,
):
    # cijene
    price_map_days = {10: 3, 30: 30, 90: 60}
    price_map_private = {"1k": 10, "5k": 30, "10k": 50, "30k": 100}

    allowed = {"btc", "ltc", "eth", "usdttrc20"}
    if pay_currency not in allowed:
        raise HTTPException(status_code=400, detail="Invalid currency")

    if not NOWPAYMENTS_API_KEY:
        raise HTTPException(status_code=500, detail="NOWPAYMENTS_API_KEY missing")
    if not NOWPAYMENTS_IPN_SECRET:
        raise HTTPException(status_code=500, detail="NOWPAYMENTS_IPN_SECRET missing")
    if not BASE_URL:
        raise HTTPException(status_code=500, detail="BASE_URL missing")

    # odredi amount + order_id + opis
    kind = (kind or "subscription").lower()

    if kind == "private_lines":
        if not package or package not in price_map_private:
            raise HTTPException(status_code=400, detail="Invalid package")
        amount_usd = price_map_private[package]
        order_id = f"pl:{user_id}:{package}"
        desc = f"Private lines package {package}"
    else:
        # default: subscription
        if days is None or days not in price_map_days:
            raise HTTPException(status_code=400, detail="Invalid plan")
        amount_usd = price_map_days[days]
        ck = (cat_key or "unknown").strip()
        order_id = f"sub:{user_id}:{ck}:{days}"
        desc = f"{days} days access ({ck})"

    payload = {
        "price_amount": amount_usd,
        "price_currency": "usd",
        "pay_currency": pay_currency,
        "order_id": order_id,
        "order_description": desc,
        "ipn_callback_url": f"{BASE_URL}/webhook/nowpayments",
    }

    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.nowpayments.io/v1/invoice", json=payload, headers=headers)

    print("NOWPayments status:", r.status_code)
    print("NOWPayments body:", r.text)

    if r.status_code not in (200, 201):
        try:
            return JSONResponse(status_code=r.status_code, content=r.json())
        except Exception:
            return JSONResponse(status_code=r.status_code, content={"error": r.text})

    data = r.json()
    invoice_url = data.get("invoice_url")
    if not invoice_url:
        return JSONResponse(status_code=502, content={"error": "Missing invoice_url", "raw": data})

    return {"invoice_url": invoice_url}

@app.post("/webhook/nowpayments")
async def nowpayments_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("x-nowpayments-sig")
    if not sig:
        raise HTTPException(status_code=403, detail="Missing signature")

    calc = hmac.new(
        NOWPAYMENTS_IPN_SECRET.encode("utf-8"),
        body,
        hashlib.sha512
    ).hexdigest()

    if sig != calc:
        raise HTTPException(status_code=403, detail="Bad signature")

    data = await request.json()
    status = (data.get("payment_status") or "").lower()

    # Obradi SAMO kad je finished (da ne dobiješ 2 poruke: confirmed + finished)
    if status != "finished":
        return {"status": "ignored_status", "payment_status": status}

    # Idempotency: ako NOWPayments pošalje isti finished više puta (retry),
    # mi odradimo samo prvi put.
    payment_id = str(
        data.get("payment_id")
        or data.get("id")
        or data.get("invoice_id")
        or ""
    )

    ok_first_time = await db.mark_payment_processed_once(payment_id)
    if not ok_first_time:
        return {"status": "duplicate_ignored", "payment_id": payment_id}

    order_id = data.get("order_id", "")

     # očekujemo:
    # - subscription: "sub:user:cat_key:days"
    # - private lines: "pl:user:package"
    parts = order_id.split(":")

    if len(parts) < 3:
        return {"status": "bad_order_id", "order_id": order_id}

    kind = parts[0]
    user_id = int(parts[1])

    if kind == "sub":
        # novi format sub:user:cat:days  (len==4)
        # legacy format sub:user:days    (len==3)
        if len(parts) == 4:
            cat_key = parts[2]
            days = int(parts[3])
        else:
            cat_key = "unknown"
            days = int(parts[2])

        now_ts = int(time.time())
        expires_at = now_ts + days * 86400

        await db.set_subscription(
            user_id,
            expires_at,
            sub_type=cat_key,
            plan_days=days,
            starts_at=now_ts,
        )

         # ✅ notify user
        await tg_send_message(
            user_id,
            "✅ <b>Payment confirmed!</b>\n\n"
            f"📦 Subscription: <b>{cat_key}</b>\n"
            f"🗓️ Plan: <b>{days} days</b>\n"
            "🔓 Access is now enabled.\n\n"
            "Tap below to return to the menu and see access button:",
            reply_markup=back_to_menu_kb()
        )

        return {"status": "ok", "kind": "sub", "cat_key": cat_key, "days": days}

    if kind == "pl":
        package = parts[2]

        price_map_private = {"1k": 10, "5k": 30, "10k": 50, "30k": 100}
        lines_map = {"1k": 1000, "5k": 5000, "10k": 10000, "30k": 30000}

        if package in price_map_private and package in lines_map:
            await db.insert_private_lines_purchase(
                user_id=user_id,
                package=package,
                lines_count=lines_map[package],
                price_usd=price_map_private[package],
                created_at=int(time.time()),
            )

            # ✅ notify user
            await tg_send_message(
                user_id,
                "✅ <b>Payment confirmed!</b>\n\n"
                f"🔐 Private lines package: <b>{package}</b>\n"
                f"📦 Lines: <b>{lines_map[package]}</b>\n"
                "📩 Message @ispodradara106 to receive lines manually.\n\n"
                "Tap below to return to the menu:",
                reply_markup=back_to_menu_kb()
            )

        return {"status": "ok", "kind": "pl", "package": package}

    return {"status": "unknown_kind", "order_id": order_id}
