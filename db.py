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

            # 1) ako postoji stara subscriptions tablica (1 row po useru), migriraj je
            await migrate_subscriptions_to_multi()

            # 2) osiguraj da nova schema postoji
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                sub_type TEXT NOT NULL DEFAULT '',
                expires_at BIGINT NOT NULL,
                plan_days BIGINT NOT NULL DEFAULT 0,
                starts_at BIGINT NOT NULL DEFAULT 0,
                UNIQUE (user_id, sub_type)
            );
            
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_payments (
                payment_id TEXT PRIMARY KEY,
                processed_at BIGINT NOT NULL
            );
            """)

            # --- add revoked_at (optional) ---
            await conn.execute("""
            ALTER TABLE subscriptions
            ADD COLUMN IF NOT EXISTS revoked_at BIGINT NOT NULL DEFAULT 0;
            """)

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

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                started_at BIGINT NOT NULL DEFAULT 0,
                last_seen BIGINT NOT NULL DEFAULT 0
            );
            """)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sub_type TEXT NOT NULL DEFAULT '',
                expires_at INTEGER NOT NULL,
                plan_days INTEGER NOT NULL DEFAULT 0,
                starts_at INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, sub_type)
            );
            """)

            # --- add revoked_at (optional) ---
            try:
                await db.execute("ALTER TABLE subscriptions ADD COLUMN revoked_at INTEGER NOT NULL DEFAULT 0;")
            except Exception:
                pass


            # ako je već postojala stara tablica bez sub_type
            try:
                await db.execute("ALTER TABLE subscriptions ADD COLUMN sub_type TEXT NOT NULL DEFAULT '';")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE subscriptions ADD COLUMN plan_days INTEGER NOT NULL DEFAULT 0;")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE subscriptions ADD COLUMN starts_at INTEGER NOT NULL DEFAULT 0;")
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

            await db.execute("""
            CREATE TABLE IF NOT EXISTS processed_payments (
                payment_id TEXT PRIMARY KEY,
                processed_at INTEGER NOT NULL
            );
            """)

            await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                started_at INTEGER NOT NULL DEFAULT 0,
                last_seen INTEGER NOT NULL DEFAULT 0
            )
            """)

            await migrate_subscriptions_to_multi()
            await db.commit()

async def migrate_subscriptions_to_multi():
    """
    Migrira staru subscriptions tablicu (user_id PRIMARY KEY)
    u novu (id PK + UNIQUE(user_id, sub_type)).
    Sigurno za SQLite i Postgres.
    """
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            # ako već ima "id" kolonu, pretpostavi da je već migrirano
            col = await conn.fetchval("""
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='subscriptions' AND column_name='id'
            """)
            if col:
                return

            # rename old
            await conn.execute("ALTER TABLE subscriptions RENAME TO subscriptions_old;")

            # new table
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                sub_type TEXT NOT NULL DEFAULT '',
                expires_at BIGINT NOT NULL,
                plan_days BIGINT NOT NULL DEFAULT 0,
                starts_at BIGINT NOT NULL DEFAULT 0,
                UNIQUE (user_id, sub_type)
            );
            """)

            # copy
            await conn.execute("""
            INSERT INTO subscriptions (user_id, sub_type, expires_at, plan_days, starts_at)
            SELECT
                user_id,
                COALESCE(sub_type,'') as sub_type,
                expires_at,
                COALESCE(plan_days,0) as plan_days,
                COALESCE(starts_at,0) as starts_at
            FROM subscriptions_old;
            """)

            await conn.execute("DROP TABLE subscriptions_old;")

    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute("PRAGMA table_info(subscriptions)")
            cols = [r[1] for r in await cur.fetchall()]
            if "id" in cols:
                return

            await db.execute("ALTER TABLE subscriptions RENAME TO subscriptions_old;")

            await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sub_type TEXT NOT NULL DEFAULT '',
                expires_at INTEGER NOT NULL,
                plan_days INTEGER NOT NULL DEFAULT 0,
                starts_at INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, sub_type)
            )
            """)

            await db.execute("""
            INSERT INTO subscriptions (user_id, sub_type, expires_at, plan_days, starts_at)
            SELECT
                user_id,
                COALESCE(sub_type,''),
                expires_at,
                COALESCE(plan_days,0),
                COALESCE(starts_at,0)
            FROM subscriptions_old;
            """)

            await db.execute("DROP TABLE subscriptions_old;")
            await db.commit()

# ---------- SUBSCRIPTIONS ----------
async def set_subscription(
    user_id: int,
    expires_at: int,
    sub_type: str = "",
    plan_days: int = 0,
    starts_at: int = 0,
):
    # plan_days = 10/30/90, starts_at = timestamp kad je aktivirano
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO subscriptions (user_id, expires_at, sub_type, plan_days, starts_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, sub_type)
            DO UPDATE SET
                expires_at = EXCLUDED.expires_at,
                plan_days = EXCLUDED.plan_days,
                starts_at = EXCLUDED.starts_at
            """, user_id, expires_at, sub_type or "", int(plan_days or 0), int(starts_at or 0))
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute(
                "INSERT INTO subscriptions (user_id, expires_at, sub_type, plan_days, starts_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, sub_type) DO UPDATE SET "
                "expires_at=excluded.expires_at, plan_days=excluded.plan_days, starts_at=excluded.starts_at",
                (user_id, expires_at, sub_type or "", int(plan_days or 0), int(starts_at or 0)),
            )
            await db.commit()


async def get_subscription_expires_at(user_id: int, sub_type: str | None = None) -> int:
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            if sub_type:
                row = await conn.fetchrow(
                    "SELECT expires_at FROM subscriptions WHERE user_id=$1 AND sub_type=$2",
                    user_id, sub_type
                )
                return int(row["expires_at"]) if row else 0
            # fallback: max expiry (korisno za /status)
            val = await conn.fetchval(
                "SELECT COALESCE(MAX(expires_at),0) FROM subscriptions WHERE user_id=$1",
                user_id
            )
            return int(val or 0)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            if sub_type:
                cur = await db.execute(
                    "SELECT expires_at FROM subscriptions WHERE user_id=? AND sub_type=?",
                    (user_id, sub_type),
                )
                row = await cur.fetchone()
                return int(row[0]) if row else 0
            cur = await db.execute(
                "SELECT COALESCE(MAX(expires_at),0) FROM subscriptions WHERE user_id=?",
                (user_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

async def get_subscription_info(user_id: int):
    """
    Returns:
      {"expires_at": int, "sub_type": str, "plan_days": int, "starts_at": int}
    or None if user doesn't exist in table.
    """
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT expires_at, sub_type, plan_days, starts_at FROM subscriptions WHERE user_id=$1",
                user_id
            )
            if not row:
                return None
            return {
                "expires_at": int(row["expires_at"]),
                "sub_type": (row["sub_type"] or ""),
                "plan_days": int(row["plan_days"] or 0),
                "starts_at": int(row["starts_at"] or 0),
            }
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute(
                "SELECT expires_at, sub_type, plan_days, starts_at FROM subscriptions WHERE user_id=?",
                (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "expires_at": int(row[0]),
                "sub_type": (row[1] or ""),
                "plan_days": int(row[2] or 0),
                "starts_at": int(row[3] or 0),
            }

async def get_user_subscriptions(user_id: int, active_only: bool = True):
    now = int(time.time())

    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch(
                    "SELECT user_id, expires_at, sub_type, plan_days, starts_at "
                    "FROM subscriptions WHERE user_id=$1 AND expires_at > $2 "
                    "ORDER BY expires_at DESC",
                    user_id, now
                )
            else:
                rows = await conn.fetch(
                    "SELECT user_id, expires_at, sub_type, plan_days, starts_at "
                    "FROM subscriptions WHERE user_id=$1 "
                    "ORDER BY expires_at DESC",
                    user_id
                )

            return [{
                "user_id": int(r["user_id"]),
                "expires_at": int(r["expires_at"]),
                "sub_type": r["sub_type"] or "",
                "plan_days": int(r["plan_days"] or 0),
                "starts_at": int(r["starts_at"] or 0),
            } for r in rows]

    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            if active_only:
                cur = await db.execute(
                    "SELECT user_id, expires_at, sub_type, plan_days, starts_at "
                    "FROM subscriptions WHERE user_id=? AND expires_at > ? "
                    "ORDER BY expires_at DESC",
                    (user_id, now),
                )
            else:
                cur = await db.execute(
                    "SELECT user_id, expires_at, sub_type, plan_days, starts_at "
                    "FROM subscriptions WHERE user_id=? "
                    "ORDER BY expires_at DESC",
                    (user_id,),
                )

            rows = await cur.fetchall()
            return [{
                "user_id": int(r[0]),
                "expires_at": int(r[1]),
                "sub_type": r[2] or "",
                "plan_days": int(r[3] or 0),
                "starts_at": int(r[4] or 0),
            } for r in rows]

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

async def get_user_subscriptions(user_id: int, active_only: bool = True):
    now = int(time.time())
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch(
                    "SELECT user_id, expires_at, sub_type, plan_days, starts_at "
                    "FROM subscriptions WHERE user_id=$1 AND expires_at > $2 "
                    "ORDER BY expires_at DESC",
                    user_id, now,
                )
            else:
                rows = await conn.fetch(
                    "SELECT user_id, expires_at, sub_type, plan_days, starts_at "
                    "FROM subscriptions WHERE user_id=$1 "
                    "ORDER BY expires_at DESC",
                    user_id,
                )
            return [{
                "user_id": int(r["user_id"]),
                "expires_at": int(r["expires_at"]),
                "sub_type": r["sub_type"] or "",
                "plan_days": int(r["plan_days"] or 0),
                "starts_at": int(r["starts_at"] or 0),
            } for r in rows]
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            if active_only:
                cur = await db.execute(
                    "SELECT user_id, expires_at, sub_type, plan_days, starts_at "
                    "FROM subscriptions WHERE user_id=? AND expires_at > ? "
                    "ORDER BY expires_at DESC",
                    (user_id, now),
                )
            else:
                cur = await db.execute(
                    "SELECT user_id, expires_at, sub_type, plan_days, starts_at "
                    "FROM subscriptions WHERE user_id=? "
                    "ORDER BY expires_at DESC",
                    (user_id,),
                )
            rows = await cur.fetchall()
            return [{
                "user_id": int(r[0]),
                "expires_at": int(r[1]),
                "sub_type": r[2] or "",
                "plan_days": int(r[3] or 0),
                "starts_at": int(r[4] or 0),
            } for r in rows]

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

async def revoke_subscription(user_id: int, sub_type: str | None = None):
    # ne briši red, nego ga označi kao revoked
    now = int(time.time())

    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            if sub_type is None:
                await conn.execute(
                    "UPDATE subscriptions SET expires_at=0, revoked_at=$2 WHERE user_id=$1",
                    user_id, now
                )
            else:
                await conn.execute(
                    "UPDATE subscriptions SET expires_at=0, revoked_at=$3 WHERE user_id=$1 AND sub_type=$2",
                    user_id, sub_type, now
                )
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            if sub_type is None:
                await db.execute(
                    "UPDATE subscriptions SET expires_at=0, revoked_at=? WHERE user_id=?",
                    (now, user_id)
                )
            else:
                await db.execute(
                    "UPDATE subscriptions SET expires_at=0, revoked_at=? WHERE user_id=? AND sub_type=?",
                    (now, user_id, sub_type)
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
                "SELECT user_id, expires_at, sub_type, revoked_at "
                "FROM subscriptions "
                "WHERE expires_at <= $1 "
                "ORDER BY revoked_at DESC, expires_at DESC "
                "LIMIT $2 OFFSET $3",
                now, limit, offset,
            )
            out = [
                {
                    "user_id": int(r["user_id"]),
                    "expires_at": int(r["expires_at"]),
                    "sub_type": r["sub_type"] or "",
                    "revoked_at": int(r["revoked_at"] or 0),
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
                "SELECT user_id, expires_at, sub_type, revoked_at "
                "FROM subscriptions "
                "WHERE expires_at <= ? "
                "ORDER BY revoked_at DESC, expires_at DESC "
                "LIMIT ? OFFSET ?",
                (now, limit, offset),
            )
            rows = await cur.fetchall()
            out = [
                {
                    "user_id": int(r[0]),
                    "expires_at": int(r[1]),
                    "sub_type": r[2] or "",
                    "revoked_at": int(r[3] or 0),
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


# ---------- USERS ----------
async def upsert_user(
    user_id: int,
    username: str = "",
    first_name: str = "",
    last_name: str = "",
    ts: int | None = None
):
    ts = int(ts or time.time())
    username = (username or "").lstrip("@")
    first_name = first_name or ""
    last_name = last_name or ""

    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, started_at, last_seen)
            VALUES ($1, $2, $3, $4, $5, $5)
            ON CONFLICT (user_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_seen = EXCLUDED.last_seen
            """, user_id, username, first_name, last_name, ts)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, started_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                last_seen=excluded.last_seen
            """, (user_id, username, first_name, last_name, ts, ts))
            await db.commit()


async def get_users_page(limit: int = 10, offset: int = 0):
    """
    Returns (rows, total)
    row: {"user_id": int, "username": str, "first_name": str, "last_name": str, "started_at": int, "last_seen": int}
    """
    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            rows = await conn.fetch(
                "SELECT user_id, username, first_name, last_name, started_at, last_seen "
                "FROM users ORDER BY last_seen DESC LIMIT $1 OFFSET $2",
                limit, offset
            )
            out = [{
                "user_id": int(r["user_id"]),
                "username": r["username"] or "",
                "first_name": r["first_name"] or "",
                "last_name": r["last_name"] or "",
                "started_at": int(r["started_at"] or 0),
                "last_seen": int(r["last_seen"] or 0),
            } for r in rows]
            return out, int(total or 0)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            cur = await db.execute("SELECT COUNT(*) FROM users")
            total = (await cur.fetchone())[0]

            cur = await db.execute(
                "SELECT user_id, username, first_name, last_name, started_at, last_seen "
                "FROM users ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cur.fetchall()
            out = [{
                "user_id": int(r[0]),
                "username": r[1] or "",
                "first_name": r[2] or "",
                "last_name": r[3] or "",
                "started_at": int(r[4] or 0),
                "last_seen": int(r[5] or 0),
            } for r in rows]
            return out, total

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
    
    async def mark_payment_processed_once(payment_id: str) -> bool:
        """
        Vrati True samo prvi put kad vidimo payment_id.
        Ako isti webhook dođe opet (retry / confirmed->finished), vrati False.
        """
    if not payment_id:
        return False

    now_ts = int(time.time())

    if DATABASE_URL:
        pool = await _pg()
        async with pool.acquire() as conn:
            got = await conn.fetchval("""
                INSERT INTO processed_payments (payment_id, processed_at)
                VALUES ($1, $2)
                ON CONFLICT (payment_id) DO NOTHING
                RETURNING payment_id;
            """, payment_id, now_ts)
            return bool(got)
    else:
        import aiosqlite
        async with aiosqlite.connect(SQLITE_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO processed_payments (payment_id, processed_at) VALUES (?, ?);",
                (payment_id, now_ts),
            )
            cur = await db.execute("SELECT changes();")
            row = await cur.fetchone()
            await db.commit()
            return bool(row and row[0] == 1)