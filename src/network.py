import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable, Optional

from zoneinfo import ZoneInfo

from config import (
    PING_TIMEOUT,
    PING_TIMEOUT_THRESHOLD,
    TARGET_IP,
    TARGET_PORT,
    TIMEZONE,
)

logger = logging.getLogger(__name__)

LightOnCallback = Callable[[float], Awaitable[None]]
LightOffCallback = Callable[[float, Optional[datetime]], Awaitable[None]]


class NetworkMonitor:

    def __init__(
        self,
        on_light_on: LightOnCallback,
        on_light_off: LightOffCallback,
        initial_state: bool = True,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        self._host = host or TARGET_IP
        self._port = port or TARGET_PORT
        self.on_light_on = on_light_on
        self.on_light_off = on_light_off
        self.current_state = initial_state
        self.first_failure_time: Optional[datetime] = None
        self._pending_alert_logged = False

    async def ping(self) -> bool:
        try:
            conn = asyncio.open_connection(self._host, self._port)
            reader, writer = await asyncio.wait_for(conn, timeout=PING_TIMEOUT)
            writer.close()
            await writer.wait_closed()
            return True
        except (OSError, asyncio.TimeoutError, TimeoutError):
            return False

    async def check(self, duration_since_last_change: float) -> None:
        success = await self.ping()
        now = datetime.now(ZoneInfo(TIMEZONE))

        if success:
            self.first_failure_time = None
            self._pending_alert_logged = False

            if not self.current_state:
                logger.info("Connection restored - triggering ON event")
                self.current_state = True
                await self.on_light_on(duration_since_last_change)
        else:
            if self.first_failure_time is None:
                self.first_failure_time = now
                logger.warning("Ping failed - starting hysteresis timer")

            elapsed = (now - self.first_failure_time).total_seconds()

            if elapsed >= PING_TIMEOUT_THRESHOLD and self.current_state:
                logger.warning(
                    f"Ping failed for {elapsed:.0f}s - triggering OFF event"
                )
                self.current_state = False
                await self.on_light_off(
                    duration_since_last_change, self.first_failure_time
                )
                self._pending_alert_logged = False

            elif self.current_state and not self._pending_alert_logged:
                remaining = PING_TIMEOUT_THRESHOLD - elapsed
                logger.info(f"Ping failed... pending alert in {remaining:.0f}s")
                self._pending_alert_logged = True