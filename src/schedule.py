import asyncio
import logging
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import aiohttp

from config import (
    GITHUB_TOKEN,
    GITHUB_REPO,
    GITHUB_IMAGE_PATH,
    GITHUB_JSON_PATH,
    SCHEDULE_GROUP,
    TIMEZONE,
)

logger = logging.getLogger(__name__)

DAY_NAMES = {
    0: "Понеділок", 1: "Вівторок", 2: "Середа",
    3: "Четвер", 4: "П'ятниця", 5: "Субота", 6: "Неділя",
}

BLACKOUT_VALUES = frozenset({"no", "first", "second", "maybe", "mfirst", "msecond"})
CONFIRMED_BLACKOUT = frozenset({"no", "first", "second"})

class OutagePeriod:
    def __init__(self, start: datetime, end: datetime):
        self.start = start
        self.end = end

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)

    def format_duration(self) -> str:
        minutes = self.duration_minutes
        if minutes >= 60:
            hours, mins = divmod(minutes, 60)
            return f"{hours}год {mins}хв" if mins > 0 else f"{hours}год"
        return f"{minutes}хв"

    def __repr__(self):
        return f"OutagePeriod({self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')})"

class ScheduleParser:
    def __init__(self, group: str = SCHEDULE_GROUP):
        self.group = group
        self.cached_data = None

    async def check_updates(self, session: aiohttp.ClientSession, last_sha: str):
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/git/refs/heads/main"
        
        params = {
            "t": int(time.time())
        }
        
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }

        try:
            async with session.get(api_url, params=params, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning(f"GitHub API Error: {resp.status}")
                    return None, None, None

                ref_data = await resp.json()
                latest_sha = ref_data.get("object", {}).get("sha")
                
                if not latest_sha:
                    return None, None, None
                    
                if latest_sha == last_sha:
                    return None, None, None

                logger.info(f"New commit detected: {latest_sha[:7]}. Fetching files...")
                
                image_bytes = await self._download_raw(session, GITHUB_IMAGE_PATH, latest_sha, False)
                json_data = await self._download_raw(session, GITHUB_JSON_PATH, latest_sha, True)

                if not image_bytes or not json_data:
                    logger.warning("Failed to download updated files.")
                    return None, None, None

                self.cached_data = json_data
                return json_data, image_bytes, latest_sha
        except Exception as e:
            logger.error(f"Error checking updates: {e}")
            return None, None, None

    async def _download_raw(self, session: aiohttp.ClientSession, path: str, sha: str, is_json: bool):
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{sha}/{path}"
        try:
            async with session.get(url, timeout=30) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None) if is_json else await resp.read()
        except Exception:
            return None

    def get_schedule_fingerprint(self, data: Dict) -> str:
        if not data or "fact" not in data:
            return ""
        try:
            fact_data = data.get("fact", {}).get("data", {})
            tz = ZoneInfo(TIMEZONE)
            now = datetime.now(tz).date()
            tomorrow = now + timedelta(days=1)
            
            relevant = {}
            for ts_str, groups in fact_data.items():
                dt = datetime.fromtimestamp(int(ts_str), tz).date()
                if dt in (now, tomorrow) and self.group in groups:
                    relevant[ts_str] = groups[self.group]
            
            data_str = json.dumps(relevant, sort_keys=True)
            return hashlib.md5(data_str.encode()).hexdigest()
        except Exception:
            return ""

    def is_full_schedule(self, data: Dict) -> bool:
        if not data or "fact" not in data:
            return False
            
        fact_data = data.get("fact", {}).get("data", {})
        tz = ZoneInfo(TIMEZONE)
        now = datetime.now(tz).date()
        tomorrow = now + timedelta(days=1)
        
        has_today = False
        has_tomorrow = False
        
        for ts_str in fact_data.keys():
            try:
                dt = datetime.fromtimestamp(int(ts_str), tz).date()
                if dt == now:
                    has_today = True
                elif dt == tomorrow:
                    has_tomorrow = True
            except (ValueError, TypeError):
                continue
                
        return has_today and has_tomorrow

    def get_day_data(self, data: Dict, date: datetime) -> Optional[Dict]:
        if not data or "fact" not in data:
            return None
        fact_data = data.get("fact", {}).get("data", {})
        target = date.date()
        for ts_str, groups in fact_data.items():
            dt = datetime.fromtimestamp(int(ts_str), ZoneInfo(TIMEZONE))
            if dt.date() == target and self.group in groups:
                return groups[self.group]
        return None

    def get_outages_for_date(self, data: Dict, date: datetime) -> List[OutagePeriod]:
        day_data = self.get_day_data(data, date)
        if not day_data: return []

        outages = []
        cur_start = cur_end = None
        tz = ZoneInfo(TIMEZONE)
        base = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)

        for hour in range(1, 25):
            val = day_data.get(str(hour), "yes")
            h_start = base + timedelta(hours=hour-1)

            if val in CONFIRMED_BLACKOUT:
                if val == "first":
                    p_s, p_e = h_start, h_start + timedelta(minutes=30)
                elif val == "second":
                    p_s, p_e = h_start + timedelta(minutes=30), h_start + timedelta(hours=1)
                else:
                    p_s, p_e = h_start, h_start + timedelta(hours=1)

                if cur_start is None:
                    cur_start, cur_end = p_s, p_e
                elif cur_end == p_s:
                    cur_end = p_e
                else:
                    outages.append(OutagePeriod(cur_start, cur_end))
                    cur_start, cur_end = p_s, p_e
            else:
                if cur_start:
                    outages.append(OutagePeriod(cur_start, cur_end))
                    cur_start = cur_end = None

        if cur_start:
            outages.append(OutagePeriod(cur_start, cur_end))
        return outages

    def get_next_outage(self, data: Dict, from_time: datetime = None) -> Optional[OutagePeriod]:
        from_time = from_time or datetime.now(ZoneInfo(TIMEZONE))
        
        for o in self.get_outages_for_date(data, from_time):
            if o.end > from_time:
                if o.start <= from_time:
                    continue
                return o
        
        tmr_date = from_time + timedelta(days=1)
        tmr_outages = self.get_outages_for_date(data, tmr_date)
        return tmr_outages[0] if tmr_outages else None

    def get_next_power_on(self, data: Dict, from_time: datetime = None) -> Optional[datetime]:
        from_time = from_time or datetime.now(ZoneInfo(TIMEZONE))
        for o in self.get_outages_for_date(data, from_time):
            if o.end > from_time: return o.end
        tmr = self.get_outages_for_date(data, from_time + timedelta(days=1))
        return tmr[0].end if tmr else None

    def format_schedule_caption(self, data: Dict, date: datetime) -> str:
        tz = ZoneInfo(TIMEZONE)
        if not date.tzinfo: date = date.replace(tzinfo=tz)
        
        d_str = date.strftime("%d.%m.%Y")
        grp = self.group.replace("GPV", "")
        lines = [f"🔖 Графік відключень <b>на сьогодні, {d_str} ({DAY_NAMES[date.weekday()]})</b>, група {grp}:"]
        
        outages = self.get_outages_for_date(data, date)
        if outages:
            for o in outages:
                lines.append(f"▪️<b>{o.start.strftime('%H:%M')} - {o.end.strftime('%H:%M')}</b> ({o.format_duration()})")
        else:
            lines.append("▪️Відключень не заплановано")
        return "\n".join(lines)

    def format_full_caption(self, data: Dict) -> str:
        tz = ZoneInfo(TIMEZONE)
        now = datetime.now(tz)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        res = [self.format_schedule_caption(data, today)]
        if self.get_day_data(data, tomorrow):
            tmr_out = self.get_outages_for_date(data, tomorrow)
            if tmr_out:
                grp = self.group.replace("GPV", "")
                res.append(f"\n🔖 Графік <b>на завтра, {tomorrow.strftime('%d.%m.%Y')} ({DAY_NAMES[tomorrow.weekday()]})</b>, група {grp}:")
                for o in tmr_out:
                    res.append(f"▪️<b>{o.start.strftime('%H:%M')} - {o.end.strftime('%H:%M')}</b> ({o.format_duration()})")
        return "\n".join(res)