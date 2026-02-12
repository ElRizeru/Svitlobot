import unittest
import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from database import DatabaseManager, init_db, close_db, log_event, log_voltage, set_state, get_state
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

if __name__ == '__main__':
    unittest.main()
