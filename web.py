import time
import os
import hmac
import hashlib
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

import db

load_dotenv()

app = FastAPI()

DRIVE_LINK = "https://drive.google.com/"  # <-- stavi svoj pravi link
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET")


@app.on_event("startup")
async def on_startup():
    await db.init_db()


@app.get("/access")
async def access(token: str):
    now = int(time.time())

    data = await db.get_token(token)
    if not data:
        raise HTTPException(status_code=403, detail="Invalid token")

    if data["expires_at"] < now:
        await db.delete_token(token)
        raise HTTPException(status_code=403, detail="Token expired")

    user_id = data["user_id"]
    sub_exp = await db.get_subscription_expires_at(user_id)

    if sub_exp < now:
        raise HTTPException(status_code=403, detail="No active access")

    html = f"""
    <html>
      <head><title>Cloud Access</title></head>
      <body style="font-family: Arial; max-width: 700px; margin: 40px auto;">
        <h2>✅ Pristup odobren</h2>
        <p>Tvoj pristup vrijedi do: <b>{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sub_exp))}</b></p>
        <p><a href="{DRIVE_LINK}" target="_blank">➡️ Otvori cloud (Google Drive)</a></p>
        <hr />
        <p style="color: #666;">Ova stranica provjerava token i pretplatu (SQLite).</p>
      </body>
    </html>
    """
    return HTMLResponse(html)

@app.post("/pay/nowpayments/create")
async def create_nowpayments_invoice(user_id: int, days: int, pay_currency: str):
    price_map = {10: 15, 30: 30, 90: 60}

    if days not in price_map:
        raise HTTPException(status_code=400, detail="Invalid plan")

    allowed = {"btc", "ltc", "eth", "usdttrc20"}
    if pay_currency not in allowed:
        raise HTTPException(status_code=400, detail="Invalid currency")

    if not NOWPAYMENTS_API_KEY:
        raise HTTPException(status_code=500, detail="NOWPAYMENTS_API_KEY missing")
    if not NOWPAYMENTS_IPN_SECRET:
        raise HTTPException(status_code=500, detail="NOWPAYMENTS_IPN_SECRET missing")
    if not BASE_URL:
        raise HTTPException(status_code=500, detail="BASE_URL missing")

    payload = {
        "price_amount": price_map[days],
        "price_currency": "usd",
        "pay_currency": pay_currency,
        "order_id": f"{user_id}:{days}",
        "order_description": f"{days} days access",
        "ipn_callback_url": f"{BASE_URL}/webhook/nowpayments",
    }

    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.nowpayments.io/v1/invoice", json=payload, headers=headers)

    if r.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=r.text)

    data = r.json()
    return {"invoice_url": data["invoice_url"]}

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

    # NOWPayments obično šalje waiting/confirming/confirmed/finished...
    if status not in {"confirmed", "finished"}:
        return {"status": "ignored"}

    order_id = data.get("order_id", "")
    if ":" not in order_id:
        return {"status": "bad_order_id"}

    user_id_str, days_str = order_id.split(":", 1)
    user_id = int(user_id_str)
    days = int(days_str)

    expires_at = int(time.time()) + days * 86400
    await db.set_subscription(user_id, expires_at)

    return {"status": "ok"}
