"""A small, thread-safe SQLite wrapper. The schema is the single source of truth."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
  persona TEXT NOT NULL DEFAULT 'balanced'
);
CREATE TABLE IF NOT EXISTS consents (
  customer_id INTEGER NOT NULL,
  channel TEXT NOT NULL,
  opted_in INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (customer_id, channel)
);
CREATE TABLE IF NOT EXISTS policies (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL,
  policy_number TEXT NOT NULL,
  product TEXT NOT NULL,
  asset TEXT NOT NULL,
  expiry_date TEXT NOT NULL,
  premium_prev INTEGER NOT NULL,
  premium_new INTEGER NOT NULL,
  sum_insured INTEGER NOT NULL,
  ncb_percent INTEGER NOT NULL DEFAULT 0,
  increase_reasons TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'open',
  renewed_at TEXT,
  renewed_plan TEXT,
  renewed_amount INTEGER
);
CREATE TABLE IF NOT EXISTS threads (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL,
  policy_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY,
  thread_id INTEGER NOT NULL,
  customer_id INTEGER NOT NULL,
  channel TEXT NOT NULL,
  direction TEXT NOT NULL,
  sender TEXT NOT NULL,
  subject TEXT,
  body TEXT NOT NULL,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL,
  thread_id INTEGER,
  message_id INTEGER,
  channel TEXT NOT NULL,
  type TEXT NOT NULL,
  meta TEXT NOT NULL DEFAULT '{}',
  ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quotes (
  id INTEGER PRIMARY KEY,
  policy_id INTEGER NOT NULL,
  thread_id INTEGER,
  plan TEXT NOT NULL,
  installments INTEGER NOT NULL,
  per_installment INTEGER NOT NULL,
  total INTEGER NOT NULL,
  surcharge INTEGER NOT NULL,
  token TEXT NOT NULL UNIQUE,
  message_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS followups (
  id INTEGER PRIMARY KEY,
  thread_id INTEGER NOT NULL,
  customer_id INTEGER NOT NULL,
  channel TEXT NOT NULL,
  due_at TEXT NOT NULL,
  note TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS handoffs (
  id INTEGER PRIMARY KEY,
  thread_id INTEGER NOT NULL,
  customer_id INTEGER NOT NULL,
  reason TEXT NOT NULL,
  summary TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolution_note TEXT
);
CREATE TABLE IF NOT EXISTS agent_runs (
  id INTEGER PRIMARY KEY,
  thread_id INTEGER NOT NULL,
  customer_id INTEGER NOT NULL,
  trigger TEXT NOT NULL,
  started_at TEXT NOT NULL,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  steps INTEGER NOT NULL DEFAULT 0,
  outcome TEXT NOT NULL DEFAULT 'running',
  summary TEXT
);
CREATE TABLE IF NOT EXISTS tool_calls (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL,
  thread_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  args TEXT NOT NULL,
  result TEXT NOT NULL,
  ok INTEGER NOT NULL,
  ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_customer ON events (customer_id, ts);
CREATE INDEX IF NOT EXISTS ix_events_message ON events (message_id, type);
CREATE INDEX IF NOT EXISTS ix_messages_thread ON messages (thread_id, id);
CREATE INDEX IF NOT EXISTS ix_threads_customer ON threads (customer_id);
CREATE INDEX IF NOT EXISTS ix_policies_customer ON policies (customer_id);
"""


class Database:
    """SQLite with a re-entrant lock so FastAPI's worker threads can share one connection."""

    def __init__(self, path: str = ":memory:"):
        self.path = path
        self._lock = threading.RLock()
        self._depth = 0
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).lastrowid or 0

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(r) for r in rows])

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
            return row[0] if row else None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._conn.execute("BEGIN")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if outer:
                    self._conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outer:
                    self._conn.execute("COMMIT")

    def reset(self) -> None:
        with self._lock:
            tables = [
                r["name"]
                for r in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for name in tables:
                self._conn.execute(f"DROP TABLE IF EXISTS {name}")
            self._conn.executescript(SCHEMA)
