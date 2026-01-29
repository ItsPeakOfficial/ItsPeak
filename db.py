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
                expires_at BIGINT NOT NULL,
                sub_type TEXT NOT NULL DEFAULT ''
            );
            """)
            # ako ti je već kreirana stara tablica bez sub_type
            try:
                await conn.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS sub_type TEXT NOT NULL DEFAULT '';")
            except Exception:
                pass

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS access_tokens (
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                expires_at BIGINT NOT NULL
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS private_lines_purchases (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                package TEXT NOT NULL,
                lines_count BIGINT NOT NULL,
                price_usd BIGINT NOT NULL,
                created_at BIGINT NOT NULL
            );
            """)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                expires_at INTEGER NOT NULL,
                sub_type TEXT NOT NULL DEFAULT ''
            )
            """)
            # ako je već postojala stara tablica bez sub_type
            try:
                await db.execute("ALTER TABLE subscriptions ADD COLUMN sub_type TEXT NOT NULL DEFAULT '';")
            except Exception:
                pass

            await db.execute("""
            CREATE TABLE IF NOT EXISTS access_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS private_lines_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                package TEXT NOT NULL,
                lines_count INTEGER NOT NULL,
                price_usd INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            """)
            await db.commit()


# ---------- SUBSCRIPTIONS ----------
async def set_subscription(user_id: int, expires_at: int, sub_type: str = ""):
    # sub_type = npr. "mail_combo", "url_cloud", "injectables"
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO subscriptions (user_id, expires_at, sub_type)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET
                expires_at = EXCLUDED.expires_at,
                sub_type = EXCLUDED.sub_type
            """, user_id, expires_at, sub_type or "")
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute(
                "INSERT INTO subscriptions (user_id, expires_at, sub_type) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at, sub_type=excluded.sub_type",
                (user_id, expires_at, sub_type or ""),
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

async def get_subscription_info(user_id: int):
    """
    Returns {"expires_at": int, "sub_type": str} or None
    """
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT expires_at, sub_type FROM subscriptions WHERE user_id=$1",
                user_id
            )
            if not row:
                return None
            return {"expires_at": int(row["expires_at"]), "sub_type": (row["sub_type"] or "")}
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute(
                "SELECT expires_at, sub_type FROM subscriptions WHERE user_id=?",
                (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {"expires_at": int(row[0]), "sub_type": (row[1] or "")}

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

# ---------- ADMIN QUERIES ----------
async def get_subscriptions_page(limit: int = 10, offset: int = 0):
    """
    ACTIVE subscriptions ONLY
    """
    now = int(time.time())

    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM subscriptions WHERE expires_at > $1",
                now,
            )
            rows = await conn.fetch(
                "SELECT user_id, expires_at, sub_type "
                "FROM subscriptions "
                "WHERE expires_at > $1 "
                "ORDER BY expires_at ASC "
                "LIMIT $2 OFFSET $3",
                now, limit, offset,
            )
            out = [
                {
                    "user_id": int(r["user_id"]),
                    "expires_at": int(r["expires_at"]),
                    "sub_type": r["sub_type"] or "",
                }
                for r in rows
            ]
            return out, int(total or 0)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE expires_at > ?",
                (now,),
            )
            total = (await cur.fetchone())[0]

            cur = await db.execute(
                "SELECT user_id, expires_at, sub_type "
                "FROM subscriptions "
                "WHERE expires_at > ? "
                "ORDER BY expires_at ASC "
                "LIMIT ? OFFSET ?",
                (now, limit, offset),
            )
            rows = await cur.fetchall()
            out = [
                {
                    "user_id": int(r[0]),
                    "expires_at": int(r[1]),
                    "sub_type": r[2] or "",
                }
                for r in rows
            ]
            return out, total

async def get_expired_subscriptions_page(limit: int = 10, offset: int = 0):
    """
    EXPIRED + UNGRANTED subscriptions
    """
    now = int(time.time())

    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM subscriptions WHERE expires_at <= $1",
                now,
            )
            rows = await conn.fetch(
                "SELECT user_id, expires_at, sub_type "
                "FROM subscriptions "
                "WHERE expires_at <= $1 "
                "ORDER BY expires_at DESC "
                "LIMIT $2 OFFSET $3",
                now, limit, offset,
            )
            out = [
                {
                    "user_id": int(r["user_id"]),
                    "expires_at": int(r["expires_at"]),
                    "sub_type": r["sub_type"] or "",
                }
                for r in rows
            ]
            return out, int(total or 0)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE expires_at <= ?",
                (now,),
            )
            total = (await cur.fetchone())[0]

            cur = await db.execute(
                "SELECT user_id, expires_at, sub_type "
                "FROM subscriptions "
                "WHERE expires_at <= ? "
                "ORDER BY expires_at DESC "
                "LIMIT ? OFFSET ?",
                (now, limit, offset),
            )
            rows = await cur.fetchall()
            out = [
                {
                    "user_id": int(r[0]),
                    "expires_at": int(r[1]),
                    "sub_type": r[2] or "",
                }
                for r in rows
            ]
            return out, total

async def insert_private_lines_purchase(user_id: int, package: str, lines_count: int, price_usd: int, created_at: int):
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO private_lines_purchases (user_id, package, lines_count, price_usd, created_at) VALUES ($1,$2,$3,$4,$5)",
                user_id, package, lines_count, price_usd, created_at
            )
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute(
                "INSERT INTO private_lines_purchases (user_id, package, lines_count, price_usd, created_at) VALUES (?,?,?,?,?)",
                (user_id, package, lines_count, price_usd, created_at),
            )
            await db.commit()


async def get_private_lines_purchases_page(limit: int = 10, offset: int = 0):
    """
    Returns: (rows, total)
    row: {"user_id": int, "package": str, "lines_count": int, "price_usd": int, "created_at": int}
    """
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM private_lines_purchases")
            rows = await conn.fetch(
                "SELECT user_id, package, lines_count, price_usd, created_at "
                "FROM private_lines_purchases ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset
            )
            out = [{
                "user_id": int(r["user_id"]),
                "package": r["package"],
                "lines_count": int(r["lines_count"]),
                "price_usd": int(r["price_usd"]),
                "created_at": int(r["created_at"]),
            } for r in rows]
            return out, int(total or 0)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute("SELECT COUNT(*) FROM private_lines_purchases")
            total_row = await cur.fetchone()
            total = int(total_row[0]) if total_row else 0

            cur = await db.execute(
                "SELECT user_id, package, lines_count, price_usd, created_at "
                "FROM private_lines_purchases ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cur.fetchall()
            out = [{
                "user_id": int(r[0]),
                "package": r[1],
                "lines_count": int(r[2]),
                "price_usd": int(r[3]),
                "created_at": int(r[4]),
            } for r in rows]
            return out, total