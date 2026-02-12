import asyncio
import io
import logging
import time
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Awaitable, Tuple

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import tinytuya
from zoneinfo import ZoneInfo

from config import (
    TUYA_ACCESS_ID,
    TUYA_ACCESS_SECRET,
    TUYA_DEVICE_ID,
    TUYA_REGION,
    TIMEZONE,
)
from database import db_manager

logger = logging.getLogger(__name__)

VoltageCallback = Callable[[float], Awaitable[None]]


class VoltageMonitor:
    def __init__(self, interval: int = 120):
        self._interval = interval
        self._callbacks: List[VoltageCallback] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._tuya_cloud: Optional[tinytuya.Cloud] = None
        self._last_voltage: Optional[float] = None

    def add_callback(self, callback: VoltageCallback) -> None:
        self._callbacks.append(callback)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Voltage monitor started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Voltage monitor stopped")

    def _get_cloud(self) -> Optional[tinytuya.Cloud]:
        if self._tuya_cloud is None:
            try:
                self._tuya_cloud = tinytuya.Cloud(
                    apiRegion=TUYA_REGION,
                    apiKey=TUYA_ACCESS_ID,
                    apiSecret=TUYA_ACCESS_SECRET,
                )
            except Exception as e:
                logger.error(f"Failed to initialize Tuya Cloud: {e}")
                return None
        return self._tuya_cloud

    def _fetch_voltage_sync(self) -> Optional[float]:
        try:
            cloud = self._get_cloud()
            if not cloud:
                return None

            result = cloud.getstatus(TUYA_DEVICE_ID)
            if not result or "result" not in result:
                self._tuya_cloud = None
                return None

            target_codes = ["va_rms", "cur_voltage", "voltage", "Voltage"]
            for item in result["result"]:
                code = item.get("code")
                value = item.get("value")

                if code in target_codes:
                    try:
                        raw_voltage = float(value)
                        # Adaptive scaling:
                        # If > 1000, assume decivolts (e.g. 2200 -> 220.0)
                        # If < 1000, assume volts (e.g. 220 -> 220.0)
                        voltage = raw_voltage / 10.0 if raw_voltage > 500 else raw_voltage
                        
                        if 100 <= voltage <= 300:
                            return voltage
                    except (ValueError, TypeError):
                        continue
            return None
        except Exception as e:
            logger.error(f"Error fetching voltage: {e}")
            self._tuya_cloud = None
            return None

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                loop = asyncio.get_running_loop()
                voltage = await loop.run_in_executor(None, self._fetch_voltage_sync)
                
                if voltage is not None:
                    self._last_voltage = voltage
                    await self._notify_callbacks(voltage)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Voltage monitor loop error: {e}")
            
            await asyncio.sleep(self._interval)

    async def _notify_callbacks(self, voltage: float) -> None:
        for callback in self._callbacks:
            try:
                await callback(voltage)
            except Exception as e:
                logger.error(f"Error in voltage callback: {e}")

    async def get_voltage_now(self) -> Optional[float]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_voltage_sync)


async def get_voltage_stats(hours: int = 24) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    end_ts = time.time()
    start_ts = end_ts - (hours * 3600)

    try:
        cursor = await db_manager.conn.execute(
            "SELECT MIN(voltage), MAX(voltage), AVG(voltage) FROM voltage_measurements "
            "WHERE timestamp >= ?",
            (start_ts,),
        )
        row = await cursor.fetchone()
        if row and row[0] is not None:
            return row[0], row[1], row[2]
    except Exception as e:
        logger.error(f"Error getting voltage stats: {e}")
    
    return None, None, None


async def generate_voltage_chart(hours: int = 24) -> Optional[bytes]:
    end_ts = time.time()
    start_ts = end_ts - (hours * 3600)

    try:
        cursor = await db_manager.conn.execute(
            "SELECT voltage, timestamp FROM voltage_measurements "
            "WHERE timestamp >= ? ORDER BY timestamp ASC",
            (start_ts,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None

        voltages = [r[0] for r in rows]
        timestamps = [datetime.fromtimestamp(r[1], tz=ZoneInfo(TIMEZONE)) for r in rows]

        plt.switch_backend('Agg')
        plt.rcParams['font.family'] = 'sans-serif'
        
        fig, ax = plt.subplots(figsize=(10, 6), dpi=100)
        
        ax.fill_between(timestamps, voltages, 190, color='#3498db', alpha=0.1, label='_nolegend_')
        
        ax.plot(timestamps, voltages, color='#2980b9', linewidth=2, label='Напруга (V)', 
                 marker='o', markersize=3, markerfacecolor='#34495e', markeredgecolor='none', alpha=0.8)
        
        ax.axhline(y=230, color='#e67e22', linestyle='--', linewidth=1.5, alpha=0.6, label='Норма 230V')
        
        ax.set_facecolor('#ffffff')
        fig.patch.set_facecolor('#ffffff')
        
        ax.grid(True, which='major', linestyle='-', color='#f0f0f0', linewidth=0.8)
        ax.grid(True, which='minor', linestyle=':', color='#f5f5f5', linewidth=0.5)
        ax.set_axisbelow(True)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=ZoneInfo(TIMEZONE)))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        
        plt.xticks(rotation=45, ha='right', fontsize=9, color='#7f8c8d')
        plt.yticks(fontsize=9, color='#7f8c8d')
        
        min_v = min(voltages) if voltages else 200
        max_v = max(voltages) if voltages else 240
        ax.set_ylim(min(195, min_v - 5), max(235, max_v + 5))
        
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.1), ncol=2, 
                  frameon=False, fontsize=10, labelcolor='#2c3e50')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#bdc3c7')
        ax.spines['bottom'].set_color('#bdc3c7')
        
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.2)
        buf.seek(0)
        plt.close(fig)
        
        return buf.getvalue()

    except Exception as e:
        logger.error(f"Error generating voltage chart: {e}")
        return None