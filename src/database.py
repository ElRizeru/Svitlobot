import logging
import time
from datetime import datetime
from typing import Any, List, Optional, Tuple

import aiosqlite

from config import TIMEZONE
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DB_FILE: str = "svitlobot.db"


class DatabaseManager:
    def __init__(self) -> None:
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        if self._conn:
            return
        self._conn = await aiosqlite.connect(DB_FILE)
        await self._init_tables()
        logger.info("Database connection established")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    async def _init_tables(self) -> None:
        if not self._conn:
            return

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS power_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at TEXT
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS voltage_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voltage REAL NOT NULL,
                timestamp REAL NOT NULL,
                message_id INTEGER,
                created_at TEXT
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await self._conn.commit()

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
             raise RuntimeError("Database not initialized. Call connect() first.")
        return self._conn


db_manager = DatabaseManager()


async def init_db() -> None:
    await db_manager.connect()


async def close_db() -> None:
    await db_manager.close()


async def log_event(event_type: str) -> None:
    timestamp = time.time()
    created_at = datetime.now(ZoneInfo(TIMEZONE)).isoformat()

    try:
        await db_manager.conn.execute(
            "INSERT INTO power_events (event_type, timestamp, created_at) "
            "VALUES (?, ?, ?)",
            (event_type, timestamp, created_at),
        )
        await db_manager.conn.commit()
        logger.info(f"Event logged: {event_type} at {created_at}")
    except Exception as e:
        logger.error(f"Failed to log event: {e}")


async def log_voltage(voltage: float, message_id: Optional[int] = None) -> None:
    timestamp = time.time()
    created_at = datetime.now(ZoneInfo(TIMEZONE)).isoformat()

    try:
        await db_manager.conn.execute(
            "INSERT INTO voltage_measurements (voltage, timestamp, message_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (voltage, timestamp, message_id, created_at),
        )
        await db_manager.conn.commit()
    except Exception as e:
        logger.error(f"Failed to log voltage: {e}")


async def get_state(key: str, default: Any = None) -> Any:
    try:
        cursor = await db_manager.conn.execute(
            "SELECT value FROM system_state WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else default
    except Exception as e:
        logger.error(f"Failed to get state {key}: {e}")
        return default


async def set_state(key: str, value: Any) -> None:
    try:
        await db_manager.conn.execute(
            "INSERT INTO system_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        await db_manager.conn.commit()
    except Exception as e:
        logger.error(f"Failed to set state {key}: {e}")


async def get_events_range(
    start_ts: float, end_ts: float
) -> List[Tuple[str, float]]:
    try:
        cursor = await db_manager.conn.execute(
            "SELECT event_type, timestamp FROM power_events "
            "WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC",
            (start_ts, end_ts),
        )
        rows = await cursor.fetchall()
        return rows
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}")
        return []