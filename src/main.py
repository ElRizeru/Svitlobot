import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, InputMediaPhoto

from zoneinfo import ZoneInfo

from config import (
    PING_INTERVAL,
    SCHEDULE_FETCH_INTERVAL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TIMEZONE,
)
from database import close_db, init_db, log_event, log_voltage, save_schedule, get_latest_schedule
from messages import (
    format_light_off_message,
    format_light_on_message,
    format_light_on_message_without_voltage,
    format_voltage_caption,
    get_current_time,
)
from network import NetworkMonitor
from schedule import ScheduleParser
from state import StateManager
from voltage import VoltageMonitor, generate_voltage_chart, get_voltage_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)


class SvitloBot:
    def __init__(self) -> None:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

        self.bot = Bot(
            token=TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.session: Optional[aiohttp.ClientSession] = None
        self.state_manager = StateManager()
        self.schedule_parser = ScheduleParser()
        self.schedule_data: Optional[Dict] = None
        self.network_monitor: Optional[NetworkMonitor] = None
        self.voltage_monitor = VoltageMonitor()
        self.voltage_monitor.add_callback(self._on_voltage_measured)
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self._current_message_id: Optional[int] = None

    async def start(self) -> None:
        logger.info("Starting Svitlobot...")
        await init_db()
        await self.state_manager.load_state()

        saved = await get_latest_schedule()
        if saved:
            self.schedule_data = saved["data"]
            logger.info("Schedule loaded from database")

        self.session = aiohttp.ClientSession()

        self.network_monitor = NetworkMonitor(
            on_light_on=self._handle_light_on,
            on_light_off=self._handle_light_off,
            initial_state=self.state_manager.state.light_on,
        )

        await self._fetch_schedule()
        
        if self.state_manager.state.light_on:
            if self.state_manager.state.last_light_message_id:
                logger.info(f"Resuming updates for message {self.state_manager.state.last_light_message_id}")
                self._current_message_id = self.state_manager.state.last_light_message_id
            
            voltage = await self.voltage_monitor.get_voltage_now()
            if voltage and self._current_message_id:
                 await self._on_voltage_measured(voltage)

            self.voltage_monitor.start()

        self._running = True

        self._tasks = [
            asyncio.create_task(self._network_monitor_loop()),
            asyncio.create_task(self._schedule_fetch_loop()),
        ]

        logger.info(f"Bot started. State: {'ON' if self.state_manager.state.light_on else 'OFF'}")

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        self._running = False
        
        await self.voltage_monitor.stop()

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self.session: await self.session.close()
        await self.bot.session.close()
        await self.state_manager.save()
        await close_db()
        logger.info("Bot stopped")

    async def _network_monitor_loop(self) -> None:
        while self._running:
            try:
                duration = self.state_manager.get_current_duration()
                await self.network_monitor.check(duration)
            except Exception:
                logger.exception("Monitor error")
                await asyncio.sleep(5)
            await asyncio.sleep(PING_INTERVAL)

    async def _schedule_fetch_loop(self) -> None:
        while self._running:
            try:
                await self._fetch_schedule()
            except Exception as e:
                logger.error(f"Schedule fetch loop error: {e}", exc_info=True)
            await asyncio.sleep(SCHEDULE_FETCH_INTERVAL)

    async def _on_voltage_measured(self, voltage: float) -> None:
        msg_id = self._current_message_id or self.state_manager.state.last_light_message_id

        if self.state_manager.state.light_on:
            await log_voltage(voltage, message_id=msg_id)

        if self._running and self.state_manager.state.light_on and msg_id:
            try:
                duration = self.state_manager.state.last_light_duration
                
                event_time = self.state_manager.state.last_change
                light_on = self.state_manager.state.light_on
                
                next_event = None
                is_tomorrow = False
                if light_on:
                    next_event, is_tomorrow = self.schedule_parser.get_next_outage(self.schedule_data) if self.schedule_data else (None, False)
                else:
                    next_event, is_tomorrow = self.schedule_parser.get_next_power_on(self.schedule_data) if self.schedule_data else (None, False)
                
                stats = await get_voltage_stats()
                chart_bytes = await generate_voltage_chart()
                
                caption = format_voltage_caption(
                    light_on, duration, voltage, stats, next_event, event_time=event_time, is_tomorrow=is_tomorrow
                )
                
                if chart_bytes:
                    try:
                        photo = BufferedInputFile(chart_bytes, filename="voltage.png")
                        await self.bot.edit_message_media(
                            chat_id=TELEGRAM_CHAT_ID,
                            message_id=msg_id,
                            media=InputMediaPhoto(media=photo, caption=caption)
                        )
                    except TelegramAPIError as e:
                        if "message can't be edited" in str(e) or "there is no media in the message" in str(e):
                            await self.bot.edit_message_text(
                                chat_id=TELEGRAM_CHAT_ID, message_id=msg_id, text=caption
                            )
                        elif "message is not modified" not in str(e):
                            logger.debug(f"Media edit error: {e}")
                else:
                    try:
                        await self.bot.edit_message_text(
                            chat_id=TELEGRAM_CHAT_ID, message_id=msg_id, text=caption
                        )
                    except TelegramAPIError as e:
                        if "message is not modified" not in str(e):
                            logger.debug(f"Text edit error: {e}")

            except Exception:
                logger.exception("Error updating message with voltage chart")

    async def _fetch_schedule(self) -> None:
        if not self.session: return

        last_sha = self.state_manager.state.last_image_commit_sha

        try:
            data, image_bytes, new_sha = await self.schedule_parser.check_updates(self.session, last_sha)

            if data and image_bytes and new_sha:
                if not self.schedule_parser.is_full_schedule(data):
                    logger.warning("Fetched schedule is incomplete (missing today or tomorrow). Skipping update.")
                    return

                new_fingerprint = self.schedule_parser.get_schedule_fingerprint(data)
                last_fingerprint = self.state_manager.state.last_schedule_fingerprint
                
                self.schedule_data = data
                filtered = self._filter_schedule_for_group(data)
                last_updated = data.get("lastUpdated", datetime.now(ZoneInfo(TIMEZONE)).isoformat())
                
                if new_fingerprint == last_fingerprint:
                    logger.info(f"Schedule for group {self.schedule_parser.group} hasn't changed. Skipping notification.")
                    await self.state_manager.update_commit_sha(new_sha)
                    
                    if self.schedule_data is None:
                        self.schedule_data = data
                        await save_schedule(filtered, last_updated)
                    
                    await self._update_light_message_schedule()
                    return

                logger.info("Schedule fingerprint changed. Sending update.")
                await self.state_manager.update_schedule_state(new_sha, new_fingerprint)
                caption = self.schedule_parser.format_full_caption(data)
                await save_schedule(filtered, last_updated, update_message=caption)
                await self._send_schedule_update(data, image_bytes)
            else:
                pass

        except Exception as e:
            logger.error(f"Error in _fetch_schedule: {e}")

    async def _send_schedule_update(self, data: Dict, image_bytes: bytes) -> None:
        try:
            caption = self.schedule_parser.format_full_caption(data)
            file_obj = BufferedInputFile(image_bytes, filename="schedule.png")
            
            logger.info("Sending schedule photo to Telegram...")
            await self.bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=file_obj, caption=caption)
            await self._update_light_message_schedule()
            logger.info("Schedule update sent successfully")
        except TelegramAPIError as e:
            logger.error(f"Failed to send schedule update: {e}")

    async def _update_light_message_schedule(self) -> None:
        message_id = self._current_message_id or self.state_manager.state.last_light_message_id
        if not message_id: return

        try:
            if self.state_manager.state.light_on:
                 voltage = await self.voltage_monitor.get_voltage_now()
                 if voltage:
                     await self._on_voltage_measured(voltage)
            else:
                duration = self.state_manager.state.last_light_duration
                event_time = self.state_manager.state.last_change
                next_on, is_tomorrow = self.schedule_parser.get_next_power_on(self.schedule_data) if self.schedule_data else (None, False)
                updated_text = format_light_off_message(duration, next_on, off_time=event_time, is_tomorrow=is_tomorrow)
                await self.bot.edit_message_text(chat_id=TELEGRAM_CHAT_ID, message_id=message_id, text=updated_text)
        except Exception as e:
            logger.debug(f"Could not update status message: {e}")

    async def _handle_light_off(self, duration: float, backdated_time: Optional[datetime]) -> None:
        event_time = backdated_time if backdated_time else get_current_time()
        logger.info(f"Light OFF. Backdated to: {event_time.strftime('%H:%M:%S')}")

        await self.state_manager.clear_light_message()
        await self.voltage_monitor.stop()
        self._current_message_id = None

        real_duration = await self.state_manager.set_light_on(False, custom_time=event_time) or duration
        await log_event("OFF")

        next_on, is_tomorrow = self.schedule_parser.get_next_power_on(self.schedule_data) if self.schedule_data else (None, False)
        msg = format_light_off_message(real_duration, next_on, off_time=event_time, is_tomorrow=is_tomorrow)

        try:
            sent_msg = await self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                
            self.state_manager.state.last_light_message_id = sent_msg.message_id
            self.state_manager.state.last_light_duration = real_duration
            await self.state_manager.save()
            self._current_message_id = sent_msg.message_id
        except TelegramAPIError:
            logger.exception("Failed to send OFF message")

    async def _handle_light_on(self, duration: float) -> None:
        event_time = datetime.now(ZoneInfo(TIMEZONE))
        logger.info("Light ON.")

        real_duration = await self.state_manager.set_light_on(True) or duration
        await log_event("ON")

        next_outage, is_tomorrow = self.schedule_parser.get_next_outage(self.schedule_data) if self.schedule_data else (None, False)
        voltage = await self.voltage_monitor.get_voltage_now()
        stats = await get_voltage_stats()
        chart_bytes = await generate_voltage_chart()
        
        initial_msg = format_voltage_caption(
            True, real_duration, voltage or 0.0, stats, next_outage, event_time=event_time, is_tomorrow=is_tomorrow
        )

        try:
            if chart_bytes:
                photo = BufferedInputFile(chart_bytes, filename="voltage_on.png")
                sent_msg = await self.bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=photo, caption=initial_msg)
            else:
                sent_msg = await self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=initial_msg)
            
            await self.state_manager.set_light_message(sent_msg.message_id, real_duration)
            self._current_message_id = sent_msg.message_id
            
            self.voltage_monitor.start()
                
        except TelegramAPIError:
            logger.exception("Failed to send ON message")
            self.voltage_monitor.start()

    def _filter_schedule_for_group(self, data: Dict) -> Dict:
        if not data or "fact" not in data:
            return data
        
        group = self.schedule_parser.group
        filtered = {
            "regionId": data.get("regionId"),
            "lastUpdated": data.get("lastUpdated"),
            "fact": {"data": {}},
        }
        
        for ts_str, groups in data.get("fact", {}).get("data", {}).items():
            if group in groups:
                filtered["fact"]["data"][ts_str] = {group: groups[group]}
        
        return filtered


async def main() -> None:
    bot = SvitloBot()
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    def signal_handler(): stop_event.set()
    for sig in (signal.SIGINT, signal.SIGTERM): loop.add_signal_handler(sig, signal_handler)
    task = asyncio.create_task(bot.start())
    await stop_event.wait()
    await bot.stop()
    try: await task
    except asyncio.CancelledError: pass

if __name__ == "__main__":
    asyncio.run(main())