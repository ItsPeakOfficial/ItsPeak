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
async def create_nowpayments_invoice(
    user_id: int,
    pay_currency: str,
    days: Optional[int] = None,
    kind: str = "subscription",
    package: Optional[str] = None,
):
    # cijene
    price_map_days = {10: 15, 30: 30, 90: 60}
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
        order_id = f"sub:{user_id}:{days}"
        desc = f"{days} days access"

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

    # NOWPayments obično šalje waiting/confirming/confirmed/finished...
    if status not in {"confirmed", "finished"}:
        return {"status": "ignored"}

    order_id = data.get("order_id", "")

    # očekujemo: "sub:user:days" ili "pl:user:package"
    parts = order_id.split(":")
    if len(parts) != 3:
        return {"status": "bad_order_id", "order_id": order_id}

    kind, user_id_str, third = parts
    user_id = int(user_id_str)

    if kind == "sub":
        days = int(third)
        expires_at = int(time.time()) + days * 86400
        await db.set_subscription(user_id, expires_at)
        return {"status": "ok", "kind": "sub"}

    if kind == "pl":
        package = third
        # za sada samo potvrdi (kasnije: delivery system / record purchase u DB)
        # možeš ovdje upisati u bazu "private_lines_purchase" tablicu, ali to ćemo kasnije.
        return {"status": "ok", "kind": "pl", "package": package}

    return {"status": "unknown_kind", "order_id": order_id}
