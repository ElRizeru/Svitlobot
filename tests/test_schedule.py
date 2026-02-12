import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
from schedule import ScheduleParser

class TestScheduleParser(unittest.TestCase):
    def setUp(self):
        self.parser = ScheduleParser(group="GPV1.1")
        self.tz = ZoneInfo("Europe/Kyiv")

    def test_is_full_schedule_valid(self):
        now = datetime.now(self.tz).date()
        today_ts = str(int(datetime(now.year, now.month, now.day, tzinfo=self.tz).timestamp()))
        tomorrow_ts = str(int(datetime(now.year, now.month, now.day, tzinfo=self.tz).timestamp() + 86400))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {"GPV1.1": {}},
                    tomorrow_ts: {"GPV1.1": {}}
                }
            }
        }
        self.assertTrue(self.parser.is_full_schedule(data))

    def test_is_full_schedule_only_today(self):
        now = datetime.now(self.tz).date()
        today_ts = str(int(datetime(now.year, now.month, now.day, tzinfo=self.tz).timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {"GPV1.1": {}}
                }
            }
        }
        self.assertFalse(self.parser.is_full_schedule(data))

    def test_is_full_schedule_only_tomorrow(self):
        now = datetime.now(self.tz).date()
        tomorrow_ts = str(int(datetime(now.year, now.month, now.day, tzinfo=self.tz).timestamp() + 86400))
        
        data = {
            "fact": {
                "data": {
                    tomorrow_ts: {"GPV1.1": {}}
                }
            }
        }
        self.assertFalse(self.parser.is_full_schedule(data))

    def test_is_full_schedule_empty(self):
        self.assertFalse(self.parser.is_full_schedule({}))
        self.assertFalse(self.parser.is_full_schedule({"fact": {"data": {}}}))

    def test_is_full_schedule_malformed_ts(self):
        data = {
            "fact": {
                "data": {
                    "not-a-timestamp": {"GPV1.1": {}}
                }
            }
        }
        self.assertFalse(self.parser.is_full_schedule(data))

    @patch('schedule.datetime')
    def test_is_full_schedule_mocked_time(self, mock_datetime):
        mock_now = datetime(2026, 2, 11, 12, 0, 0, tzinfo=self.tz)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromtimestamp.side_effect = lambda ts, tz: datetime.fromtimestamp(ts, tz)
        
        data = {
            "fact": {
                "data": {
                    "1770760800": {"GPV1.1": {}},
                    "1770847200": {"GPV1.1": {}}
                }
            }
        }
        self.assertTrue(self.parser.is_full_schedule(data))

if __name__ == '__main__':
    unittest.main()
