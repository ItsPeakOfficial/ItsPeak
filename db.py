import time
import aiosqlite

DB_PATH = "app.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            expires_at INTEGER NOT NULL
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS access_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
        """)
        await db.commit()

# --- subscriptions ---
async def set_subscription(user_id: int, expires_at: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO subscriptions (user_id, expires_at) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at",
            (user_id, expires_at),
        )
        await db.commit()

async def get_subscription_expires_at(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT expires_at FROM subscriptions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

# --- tokens ---
async def create_token(user_id: int, ttl_seconds: int = 600) -> str:
    import secrets
    token = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + ttl_seconds

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO access_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        await db.commit()

    return token

async def get_token(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, expires_at FROM access_tokens WHERE token=?",
            (token,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {"user_id": int(row[0]), "expires_at": int(row[1])}

async def delete_token(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM access_tokens WHERE token=?", (token,))
        await db.commit()

async def cleanup_expired_tokens():
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM access_tokens WHERE expires_at < ?", (now,))
        await db.commit()
