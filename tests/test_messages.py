import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from messages import format_duration, format_time, format_light_off_message, format_light_on_message, format_voltage_caption
from schedule import OutagePeriod
from config import TIMEZONE

class TestMessages(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(30), "30сек")
        self.assertEqual(format_duration(60), "1хв")
        self.assertEqual(format_duration(3600), "1год")
        self.assertEqual(format_duration(3660), "1год 1хв")
        self.assertEqual(format_duration(7200), "2год")

    def test_format_time(self):
        dt = datetime(2026, 2, 11, 15, 30, tzinfo=ZoneInfo(TIMEZONE))
        self.assertEqual(format_time(dt), "15:30")

    def test_format_light_off_message(self):
        off_time = datetime(2026, 2, 11, 10, 0, tzinfo=ZoneInfo(TIMEZONE))
        next_on = datetime(2026, 2, 11, 12, 0, tzinfo=ZoneInfo(TIMEZONE))
        msg = format_light_off_message(3600, next_power_on=next_on, off_time=off_time)
        self.assertIn("10:00 Світло зникло", msg)
        self.assertIn("Воно було <b>1год</b>", msg)

    def test_format_light_on_message(self):
        event_time = datetime(2026, 2, 11, 12, 0, tzinfo=ZoneInfo(TIMEZONE))
        outage = OutagePeriod(
            start=datetime(2026, 2, 11, 14, 0, tzinfo=ZoneInfo(TIMEZONE)),
            end=datetime(2026, 2, 11, 16, 0, tzinfo=ZoneInfo(TIMEZONE))
        )
        msg = format_light_on_message(7200, next_outage=outage, voltage=230.5, event_time=event_time)
        self.assertIn("12:00 Світло з'явилося", msg)
        self.assertIn("Його не було <b>2год</b>", msg)
        self.assertIn("Наступне планове: <b>14:00 - 16:00</b>", msg)
        self.assertIn("Напруга в мережі: <b>230.5V</b>", msg)

if __name__ == '__main__':
    unittest.main()
