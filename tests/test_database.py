import unittest
import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from database import (
    DatabaseManager, init_db, close_db,
    log_event, log_voltage, set_state, get_state,
    save_schedule, get_latest_schedule,
)
from config import TIMEZONE

class TestDatabase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_db = "test_svitlobot.db"
        import database
        self.original_db_file = database.DB_FILE
        database.DB_FILE = self.test_db
        
        await database.db_manager.close()
        await init_db()

    async def asyncTearDown(self):
        await close_db()
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        import database
        database.DB_FILE = self.original_db_file

    async def test_log_event(self):
        await log_event("TEST_ON")
        import database
        cursor = await database.db_manager.conn.execute("SELECT event_type FROM power_events")
        row = await cursor.fetchone()
        self.assertEqual(row[0], "TEST_ON")

    async def test_state_management(self):
        await set_state("test_key", "test_value")
        val = await get_state("test_key")
        self.assertEqual(val, "test_value")
        
        await set_state("test_key", "new_value")
        val = await get_state("test_key")
        self.assertEqual(val, "new_value")

    async def test_log_voltage(self):
        await log_voltage(220.5, message_id=123)
        import database
        cursor = await database.db_manager.conn.execute("SELECT voltage, message_id FROM voltage_measurements")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 220.5)
        self.assertEqual(row[1], 123)

    async def test_save_and_get_schedule(self):
        schedule_data = {
            "regionId": "kyiv-region",
            "lastUpdated": "2026-02-18T18:00:00Z",
            "fact": {"data": {"1771365600": {"GPV6.2": {"1": "yes", "2": "no"}}}},
        }
        await save_schedule(schedule_data, "2026-02-18T18:00:00Z", update_message="Test caption")

        result = await get_latest_schedule()
        self.assertIsNotNone(result)
        self.assertEqual(result["data"]["regionId"], "kyiv-region")
        self.assertEqual(result["last_updated"], "2026-02-18T18:00:00Z")
        self.assertEqual(result["update_message"], "Test caption")

    async def test_get_latest_schedule_empty(self):
        result = await get_latest_schedule()
        self.assertIsNone(result)

    async def test_save_schedule_returns_latest(self):
        await save_schedule({"v": 1}, "2026-01-01T00:00:00Z")
        await save_schedule({"v": 2}, "2026-02-01T00:00:00Z", update_message="newer")

        result = await get_latest_schedule()
        self.assertIsNotNone(result)
        self.assertEqual(result["data"]["v"], 2)
        self.assertEqual(result["update_message"], "newer")

if __name__ == '__main__':
    unittest.main()
