import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from zoneinfo import ZoneInfo

from config import TIMEZONE
from database import get_state, set_state

logger = logging.getLogger(__name__)


@dataclass
class BotState:

    light_on: bool = True
    last_change_timestamp: float = 0.0
    last_image_commit_sha: str = ""
    last_schedule_fingerprint: str = "" 
    last_light_message_id: Optional[int] = None
    last_light_duration: float = 0.0
    schedule_data: Optional[Dict] = None

    @property
    def last_change(self) -> datetime:
        if self.last_change_timestamp == 0.0:
            return datetime.now(ZoneInfo(TIMEZONE))
        return datetime.fromtimestamp(self.last_change_timestamp, ZoneInfo(TIMEZONE))

    def set_last_change(self, dt: datetime) -> None:
        self.last_change_timestamp = dt.timestamp()


class StateManager:

    def __init__(self) -> None:
        self.state: BotState = BotState()

    async def load_state(self) -> None:
        try:
            state_json = await get_state("bot_state")
            
            if state_json:
                data = json.loads(state_json)
                self.state = BotState(
                    light_on=data.get("light_on", True),
                    last_change_timestamp=data.get("last_change_timestamp", 0.0),
                    last_image_commit_sha=data.get("last_image_commit_sha", ""),
                    last_schedule_fingerprint=data.get("last_schedule_fingerprint", ""),
                    last_light_message_id=data.get("last_light_message_id"),
                    last_light_duration=data.get("last_light_duration", 0.0),
                    schedule_data=data.get("schedule_data"),
                )
                logger.info("State loaded from database")
            else:
                logger.info("No state found in database, using defaults")
                self.state.set_last_change(datetime.now(ZoneInfo(TIMEZONE)))

        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            self.state = BotState()
            self.state.set_last_change(datetime.now(ZoneInfo(TIMEZONE)))

    async def save(self) -> None:
        try:
            data = asdict(self.state)
            await set_state("bot_state", json.dumps(data))
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    async def set_schedule_data(self, data: Dict) -> None:
        self.state.schedule_data = data
        await self.save()

    async def set_light_on(
        self, is_on: bool, custom_time: Optional[datetime] = None
    ) -> Optional[float]:
        if self.state.light_on == is_on:
            return None

        now = custom_time if custom_time else datetime.now(ZoneInfo(TIMEZONE))
        duration_seconds = (now - self.state.last_change).total_seconds()

        self.state.light_on = is_on
        self.state.set_last_change(now)
        await self.save()

        return duration_seconds

    async def update_commit_sha(self, sha: str) -> None:
        self.state.last_image_commit_sha = sha
        await self.save()

    async def update_schedule_state(self, sha: str, fingerprint: str) -> None:
        self.state.last_image_commit_sha = sha
        self.state.last_schedule_fingerprint = fingerprint
        await self.save()

    def get_current_duration(self) -> float:
        now = datetime.now(ZoneInfo(TIMEZONE))
        return (now - self.state.last_change).total_seconds()

    async def set_light_message(self, message_id: int, duration: float) -> None:
        self.state.last_light_message_id = message_id
        self.state.last_light_duration = duration
        await self.save()

    async def clear_light_message(self) -> None:
        self.state.last_light_message_id = None
        self.state.last_light_duration = 0.0
        await self.save()