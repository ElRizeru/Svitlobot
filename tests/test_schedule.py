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

    def test_get_next_power_on_delayed(self):
        # Scenario: Outage 07:00-14:00. Current time 14:37. Next Outage 17:30.
        # Expectation: Return 14:00 (Start of current light slot), not 00:00.
        
        current_time = datetime(2026, 2, 12, 14, 37, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        # Build mock data
        # Keys 1-24. 
        # 1-7 (00-07): "yes" (Lights ON)
        # 8-14 (07-14): "no" (Outage)
        # 15-17 (14-17): "yes" (Lights ON)
        # 18 (17-18): "second" (17:30-18:00 Outage)
        # 19-24 (18-24): "no" (Outage)
        
        data_map = {}
        for h in range(1, 25):
            if 1 <= h <= 7:
                data_map[str(h)] = "yes"
            elif 8 <= h <= 14:
                data_map[str(h)] = "no" # OUTAGE
            elif 15 <= h <= 17:
                data_map[str(h)] = "yes" # LIGHT
            elif h == 18:
                data_map[str(h)] = "second" # 17:30-18:00 outage
            else: # 19-24
                data_map[str(h)] = "no" # OUTAGE

        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": data_map
                    }
                }
            }
        }
        
        result_date = self.parser.get_next_power_on(data, from_time=current_time)
        expected_time = today_date.replace(hour=14, minute=0)
        
        self.assertIsNotNone(result_date)
        self.assertEqual(result_date, expected_time)

if __name__ == '__main__':
    unittest.main()
