import os
import time
import secrets

DATABASE_URL = os.getenv("DATABASE_URL")  # Railway Postgres
SQLITE_PATH = os.getenv("SQLITE_PATH", "app.db")

_pg_pool = None


# ---------- CONNECTION ----------
async def _pg():
    global _pg_pool
    if _pg_pool is None:
        import asyncpg
        _pg_pool = await asyncpg.create_pool(DATABASE_URL)
    return _pg_pool


# ---------- INIT ----------
async def init_db():
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id BIGINT PRIMARY KEY,
                expires_at BIGINT NOT NULL
            );
            """)
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS access_tokens (
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                expires_at BIGINT NOT NULL
            );
            """)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
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


# ---------- SUBSCRIPTIONS ----------
async def set_subscription(user_id: int, expires_at: int):
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO subscriptions (user_id, expires_at)
            VALUES ($1, $2)
            ON CONFLICT (user_id)
            DO UPDATE SET expires_at = EXCLUDED.expires_at
            """, user_id, expires_at)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute(
                "INSERT INTO subscriptions (user_id, expires_at) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at",
                (user_id, expires_at),
            )
            await db.commit()


async def get_subscription_expires_at(user_id: int) -> int:
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT expires_at FROM subscriptions WHERE user_id=$1",
                user_id
            )
            return int(row["expires_at"]) if row else 0
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute(
                "SELECT expires_at FROM subscriptions WHERE user_id=?",
                (user_id,)
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0


# ---------- TOKENS ----------
async def create_token(user_id: int, ttl_seconds: int = 600) -> str:
    token = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + ttl_seconds

    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO access_tokens (token, user_id, expires_at) VALUES ($1, $2, $3)",
                token, user_id, expires_at
            )
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute(
                "INSERT INTO access_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires_at),
            )
            await db.commit()

    return token


async def get_token(token: str):
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, expires_at FROM access_tokens WHERE token=$1",
                token
            )
            if not row:
                return None
            return {"user_id": int(row["user_id"]), "expires_at": int(row["expires_at"])}
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute(
                "SELECT user_id, expires_at FROM access_tokens WHERE token=?",
                (token,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {"user_id": int(row[0]), "expires_at": int(row[1])}


async def delete_token(token: str):
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM access_tokens WHERE token=$1",
                token
            )
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute(
                "DELETE FROM access_tokens WHERE token=?",
                (token,),
            )
            await db.commit()


async def cleanup_expired_tokens():
    now = int(time.time())
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM access_tokens WHERE expires_at < $1",
                now
            )
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute(
                "DELETE FROM access_tokens WHERE expires_at < ?",
                (now,),
            )
            await db.commit()
