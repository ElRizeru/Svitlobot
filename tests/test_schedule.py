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

    def test_get_next_power_on_returns_tuple(self):
        current_time = datetime(2026, 2, 12, 10, 0, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": {
                            "9": "no",   # 08:00-09:00
                            "10": "no",  # 09:00-10:00
                            "11": "no",  # 10:00-11:00
                        }
                    }
                }
            }
        }
        
        result = self.parser.get_next_power_on(data, from_time=current_time)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_get_next_power_on_inside_outage(self):
        current_time = datetime(2026, 2, 12, 9, 30, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": {
                            "9": "no",   # 08:00-09:00
                            "10": "no",  # 09:00-10:00
                            "11": "no",  # 10:00-11:00
                        }
                    }
                }
            }
        }
        
        result, is_tomorrow = self.parser.get_next_power_on(data, from_time=current_time)
        self.assertIsNotNone(result)
        self.assertEqual(result, today_date.replace(hour=11, minute=0))
        self.assertFalse(is_tomorrow)

    def test_get_next_power_on_delayed(self):
        current_time = datetime(2026, 2, 12, 14, 37, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        data_map = {}
        for h in range(1, 25):
            if 1 <= h <= 7:
                data_map[str(h)] = "yes"
            elif 8 <= h <= 14:
                data_map[str(h)] = "no"
            elif 15 <= h <= 17:
                data_map[str(h)] = "yes"
            elif h == 18:
                data_map[str(h)] = "second"
            else:
                data_map[str(h)] = "no"

        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": data_map
                    }
                }
            }
        }
        
        result, is_tomorrow = self.parser.get_next_power_on(data, from_time=current_time)
        expected_time = today_date.replace(hour=14, minute=0)
        
        self.assertIsNotNone(result)
        self.assertEqual(result, expected_time)
        self.assertFalse(is_tomorrow)

    def test_get_next_power_on_between_outages(self):
        current_time = datetime(2026, 2, 12, 12, 0, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": {
                            "9": "no",   # 08:00-09:00
                            "10": "no",  # 09:00-10:00
                            "11": "no",  # 10:00-11:00
                            # gap 11:00-14:00 (current_time = 12:00)
                            "15": "no",  # 14:00-15:00
                            "16": "no",  # 15:00-16:00
                        }
                    }
                }
            }
        }
        
        result, is_tomorrow = self.parser.get_next_power_on(data, from_time=current_time)
        self.assertIsNotNone(result)
        self.assertEqual(result, today_date.replace(hour=11, minute=0))
        self.assertFalse(is_tomorrow)

    def test_get_next_power_on_no_outages_today(self):
        current_time = datetime(2026, 2, 12, 12, 0, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": {}
                    }
                }
            }
        }
        
        result, is_tomorrow = self.parser.get_next_power_on(data, from_time=current_time)
        self.assertIsNone(result)
        self.assertFalse(is_tomorrow)

    def test_get_next_outage_returns_tuple(self):
        current_time = datetime(2026, 2, 13, 10, 0, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": {
                            "15": "no",  # 14:00-15:00
                        }
                    }
                }
            }
        }
        
        result = self.parser.get_next_outage(data, from_time=current_time)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_get_next_outage_ongoing(self):
        current_time = datetime(2026, 2, 13, 14, 30, 9, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": {
                            "15": "second",  # 14:30-15:00
                            "16": "no",      # 15:00-16:00
                            "17": "no",      # 16:00-17:00
                        }
                    }
                }
            }
        }
        
        outage, is_tomorrow = self.parser.get_next_outage(data, from_time=current_time)
        self.assertIsNotNone(outage)
        self.assertEqual(outage.start, today_date.replace(hour=14, minute=30))
        self.assertEqual(outage.end, today_date.replace(hour=17, minute=0))
        self.assertFalse(is_tomorrow)

    def test_get_next_outage_started_but_not_ended(self):
        current_time = datetime(2026, 2, 13, 14, 30, 9, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        # Schedule: 00:00-00:30, 04:00-07:30, 08:00-11:00, 14:30-21:30
        data_map = {}
        data_map["1"] = "first"     # 00:00-00:30
        for h in range(2, 5):
            data_map[str(h)] = "yes"
        data_map["5"] = "no"        # 04:00-05:00
        data_map["6"] = "no"        # 05:00-06:00
        data_map["7"] = "no"        # 06:00-07:00
        data_map["8"] = "first"     # 07:00-07:30
        data_map["9"] = "no"        # 08:00-09:00
        data_map["10"] = "no"       # 09:00-10:00
        data_map["11"] = "no"       # 10:00-11:00
        for h in range(12, 15):
            data_map[str(h)] = "yes"
        data_map["15"] = "second"   # 14:30-15:00
        for h in range(16, 22):
            data_map[str(h)] = "no"
        data_map["22"] = "first"    # 21:00-21:30
        for h in range(23, 25):
            data_map[str(h)] = "yes"
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": data_map
                    }
                }
            }
        }
        
        outage, is_tomorrow = self.parser.get_next_outage(data, from_time=current_time)
        self.assertIsNotNone(outage)
        self.assertEqual(outage.start, today_date.replace(hour=14, minute=30))
        self.assertEqual(outage.end, today_date.replace(hour=21, minute=30))
        self.assertFalse(is_tomorrow)

    def test_get_next_outage_all_today_done_tomorrow(self):
        current_time = datetime(2026, 2, 13, 23, 0, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_date = today_date + timedelta(days=1)
        today_ts = str(int(today_date.timestamp()))
        tomorrow_ts = str(int(tomorrow_date.timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": {
                            "9": "no",   # 08:00-09:00 (already done)
                            "10": "no",  # 09:00-10:00 (already done)
                        }
                    },
                    tomorrow_ts: {
                        "GPV1.1": {
                            "5": "no",   # 04:00-05:00
                            "6": "no",   # 05:00-06:00
                            "7": "no",   # 06:00-07:00
                            "8": "first",# 07:00-07:30
                        }
                    }
                }
            }
        }
        
        outage, is_tomorrow = self.parser.get_next_outage(data, from_time=current_time)
        self.assertIsNotNone(outage)
        self.assertEqual(outage.start, tomorrow_date.replace(hour=4, minute=0))
        self.assertEqual(outage.end, tomorrow_date.replace(hour=7, minute=30))
        self.assertTrue(is_tomorrow)

    def test_get_next_outage_no_outages_at_all(self):
        current_time = datetime(2026, 2, 13, 12, 0, tzinfo=self.tz)
        today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = str(int(today_date.timestamp()))
        
        data = {
            "fact": {
                "data": {
                    today_ts: {
                        "GPV1.1": {}
                    }
                }
            }
        }
        
        outage, is_tomorrow = self.parser.get_next_outage(data, from_time=current_time)
        self.assertIsNone(outage)
        self.assertFalse(is_tomorrow)

if __name__ == '__main__':
    unittest.main()
