import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

import db

load_dotenv()

app = FastAPI()

DRIVE_LINK = "https://drive.google.com/"  # <-- stavi svoj pravi link


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
