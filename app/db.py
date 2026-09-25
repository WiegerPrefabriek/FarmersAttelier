"""SQLite-laag: verbinding, schema, kleine helpers.

Ontwerp:
- WAL-modus + busy_timeout, zodat lezers en de ene schrijver elkaar niet blokkeren.
- Elke aanroep opent een korte verbinding (goedkoop in SQLite) — geen gedeelde
  verbinding over threads, dus geen "objects created in a thread…"-fouten.
- Schrijfacties lopen door één RLock: de HTTP-server is multithreaded en de
  pipeline draait in een achtergrondthread.
- Alle JSON-kolommen worden als tekst opgeslagen; `loads()`/`dumps()` hier houden dat op
  één plek.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import threading
from contextlib import contextmanager

import config

_WRITE_LOCK = threading.RLock()
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

# Alleen voor mock-data en tests: een vaste "nu", zodat gesprekken over de afgelopen
# weken verspreid kunnen worden. In productie altijd None.
_FAKE_NOW: str | None = None


def now() -> str:
    if _FAKE_NOW:
        return _FAKE_NOW
    t = _dt.datetime.utcnow()
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def parse_ts(waarde: str | None) -> _dt.datetime | None:
    if not waarde:
        return None
    w = waarde.replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(w, fmt)
        except ValueError:
            continue
    return None


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def loads(tekst, default=None):
    if tekst is None or tekst == "":
        return default
    if not isinstance(tekst, str):
        return tekst
    try:
        return json.loads(tekst)
    except ValueError:
        return default


def _connect(pad: str | None = None) -> sqlite3.Connection:
    pad = pad or config.DB_PATH
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    conn = sqlite3.connect(pad, timeout=10, isolation_level=None)  # autocommit; tx() regelt BEGIN
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def tx():
    """Schrijftransactie. Gebruik: with db.tx() as c: c.execute(...)"""
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()


@contextmanager
def ro():
    """Leesverbinding."""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def rows(sql: str, params=()) -> list[dict]:
    with ro() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def one(sql: str, params=()) -> dict | None:
    with ro() as c:
        r = c.execute(sql, params).fetchone()
        return dict(r) if r else None


def scalar(sql: str, params=()):
    with ro() as c:
        r = c.execute(sql, params).fetchone()
        return r[0] if r else None


def execute(sql: str, params=()) -> int:
    """Eén schrijfstatement; geeft lastrowid terug."""
    with tx() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


_MET_CREATED_AT = {"conversations", "messages", "events", "ai_analyses", "ai_drafts", "pending_actions",
                   "learning_records", "customers", "inbound_queue", "rules"}


def insert(tabel: str, waarden: dict, conn: sqlite3.Connection | None = None) -> int:
    if _FAKE_NOW and tabel in _MET_CREATED_AT and "created_at" not in waarden:
        waarden = dict(waarden, created_at=_FAKE_NOW)  # mock/tests: datums verspreid over de tijd
    kolommen = ", ".join(waarden.keys())
    placeholders = ", ".join("?" for _ in waarden)
    sql = f"INSERT INTO {tabel} ({kolommen}) VALUES ({placeholders})"
    params = tuple(dumps(v) if isinstance(v, (dict, list)) else v for v in waarden.values())
    if conn is not None:
        return conn.execute(sql, params).lastrowid
    return execute(sql, params)


def update(tabel: str, id_: int, waarden: dict, conn: sqlite3.Connection | None = None) -> None:
    if not waarden:
        return
    if "updated_at" not in waarden and tabel in ("conversations", "customers", "rules", "knowledge_articles"):
        waarden = dict(waarden, updated_at=now())
    sets = ", ".join(f"{k} = ?" for k in waarden)
    params = tuple(dumps(v) if isinstance(v, (dict, list)) else v for v in waarden.values()) + (id_,)
    sql = f"UPDATE {tabel} SET {sets} WHERE id = ?"
    if conn is not None:
        conn.execute(sql, params)
    else:
        execute(sql, params)


def setting(key: str, default=None):
    r = one("SELECT value FROM settings WHERE key = ?", (key,))
    return loads(r["value"], r["value"]) if r else default


def set_setting(key: str, value) -> None:
    execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, dumps(value)))


def init_db() -> None:
    """Maakt het schema aan (idempotent) en zet standaardinstellingen."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = f.read()
    with _WRITE_LOCK:
        conn = _connect()
        try:
            conn.executescript(schema)
            if not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                conn.execute("INSERT INTO users(name, email, role) VALUES (?, ?, ?)",
                             ("Wieger", "wieger@farmersatelier.nl", "admin"))
                conn.execute("INSERT INTO users(name, email, role) VALUES (?, ?, ?)",
                             ("Broer", "info@farmersatelier.nl", "agent"))
            if not conn.execute("SELECT 1 FROM settings WHERE key = 'ai_mode'").fetchone():
                conn.execute("INSERT INTO settings(key, value) VALUES ('ai_mode', '\"auto\"')")
            if not conn.execute("SELECT 1 FROM settings WHERE key = 'tone'").fetchone():
                conn.execute("INSERT INTO settings(key, value) VALUES ('tone', ?)",
                             (dumps("vriendelijk, informeel (je/jij), kort, concreet, Nederlands tenzij de klant een andere taal gebruikt"),))
        finally:
            conn.close()


def db_size_mb() -> float:
    try:
        return round(os.path.getsize(config.DB_PATH) / 1_048_576, 2)
    except OSError:
        return 0.0
