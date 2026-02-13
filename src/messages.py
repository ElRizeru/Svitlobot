from datetime import datetime
from typing import Optional, Tuple

from zoneinfo import ZoneInfo

from config import TIMEZONE
from schedule import OutagePeriod


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}сек"

    minutes = round(seconds / 60)

    if minutes < 60:
        return f"{minutes}хв"

    hours = minutes // 60
    mins = minutes % 60

    if mins > 0:
        return f"{hours}год {mins}хв"
    return f"{hours}год"


def get_current_time() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def format_light_off_message(
    duration_seconds: float,
    next_power_on: Optional[datetime] = None,
    off_time: Optional[datetime] = None,
) -> str:

    event_time = off_time if off_time else get_current_time()
    time_str = format_time(event_time)
    duration_str = format_duration(duration_seconds)

    lines = [
        f"🔴 <b>{time_str} Світло зникло</b>",
        f"🕓 Воно було <b>{duration_str}</b>",
    ]

    if next_power_on:
        next_on_str = format_time(next_power_on)
        lines.append(f"🗓 Очікуємо за графіком о <b>{next_on_str}</b>")

    return "\n".join(lines)


def format_light_on_message(
    duration_seconds: float,
    next_outage: Optional[OutagePeriod] = None,
    voltage: Optional[float] = None,
    voltage_time: Optional[datetime] = None,
    event_time: Optional[datetime] = None,
) -> str:

    now = get_current_time()
    header_time = event_time if event_time else now
    time_str = format_time(header_time)
    duration_str = format_duration(duration_seconds)

    lines = [
        f"🟢 <b>{time_str} Світло з'явилося</b>",
        f"🕓 Його не було <b>{duration_str}</b>",
    ]

    if next_outage:
        start_str = format_time(next_outage.start)
        end_str = format_time(next_outage.end)
        lines.append(f"🗓 Наступне планове: <b>{start_str} - {end_str}</b>")

    if voltage is not None and voltage > 0:
        v_time = voltage_time or now
        v_time_str = format_time(v_time)
        lines.append(f"⚡️ Напруга в мережі: <b>{voltage:.1f}V</b> ({v_time_str})")
    else:
        lines.append("⚡️ Напруга в мережі: немає даних")

    return "\n".join(lines)


def format_light_on_message_without_voltage(
    duration_seconds: float,
    next_outage: Optional[OutagePeriod] = None,
    event_time: Optional[datetime] = None,
) -> str:

    now = get_current_time()
    header_time = event_time if event_time else now
    time_str = format_time(header_time)
    duration_str = format_duration(duration_seconds)

    lines = [
        f"🟢 <b>{time_str} Світло з'явилося</b>",
        f"🕓 Його не було <b>{duration_str}</b>",
    ]

    if next_outage:
        start_str = format_time(next_outage.start)
        end_str = format_time(next_outage.end)
        lines.append(f"🗓 Наступне планове: <b>{start_str} - {end_str}</b>")

    lines.append("⚡️ Напруга в мережі: зчитування...")

    return "\n".join(lines)


def format_voltage_caption(
    light_on: bool,
    duration_seconds: float,
    voltage: float,
    stats: Tuple[Optional[float], Optional[float], Optional[float]],
    next_event: Optional[datetime | OutagePeriod] = None,
    event_time: Optional[datetime] = None,
) -> str:
    now = get_current_time()
    header_time = event_time if event_time else now
    time_str = format_time(header_time)
    duration_str = format_duration(duration_seconds)
    
    status_icon = "🟢" if light_on else "🔴"
    status_text = "Світло з'явилося" if light_on else "Світло зникло"
    period_text = "Його не було" if light_on else "Воно було"
    
    lines = [
        f"{status_icon} <b>{time_str} {status_text}</b>",
        f"🕓 {period_text} <b>{duration_str}</b>",
    ]

    if next_event:
        if isinstance(next_event, OutagePeriod):
            start_str = format_time(next_event.start)
            end_str = format_time(next_event.end)
            lines.append(f"🗓 Наступне планове: <b>{start_str} - {end_str}</b>")
        else:
            next_on_str = format_time(next_event)
            lines.append(f"🗓 Очікуємо за графіком о <b>{next_on_str}</b>")

    lines.append(f"\n⚡️ Напруга: <b>{voltage:.1f} V</b>")
    
    min_v, max_v, avg_v = stats
    if min_v is not None:
        lines.extend([
            f"\n📊 За 24 год:",
            f"• Мін: <b>{min_v:.1f} V</b>",
            f"• Макс: <b>{max_v:.1f} V</b>",
            f"• Середнє: <b>{avg_v:.1f} V</b>",
        ])
    
    lines.append(f"\n🕒 Оновлено: {now.strftime('%d.%m.%Y, %H:%M:%S')}")
    
    return "\n".join(lines)