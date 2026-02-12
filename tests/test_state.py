import unittest
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo
from state import StateManager, BotState
from config import TIMEZONE

class TestStateManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = StateManager()
        self.tz = ZoneInfo(TIMEZONE)

    @patch('state.get_state', new_callable=AsyncMock)
    async def test_load_state_existing(self, mock_get_state):
        data = {
            "light_on": False,
            "last_change_timestamp": 1770760800.0,
            "last_image_commit_sha": "abc",
            "last_schedule_fingerprint": "def",
        }
        mock_get_state.return_value = json.dumps(data)
        
        await self.manager.load_state()
        
        self.assertFalse(self.manager.state.light_on)
        self.assertEqual(self.manager.state.last_change_timestamp, 1770760800.0)
        self.assertEqual(self.manager.state.last_image_commit_sha, "abc")

    @patch('state.set_state', new_callable=AsyncMock)
    async def test_save_state(self, mock_set_state):
        self.manager.state.light_on = True
        self.manager.state.last_image_commit_sha = "test-sha"
        
        await self.manager.save()
        
        mock_set_state.assert_called_once()
        saved_data = json.loads(mock_set_state.call_args[0][1])
        self.assertTrue(saved_data["light_on"])
        self.assertEqual(saved_data["last_image_commit_sha"], "test-sha")

    @patch('state.set_state', new_callable=AsyncMock)
    async def test_set_light_on_off(self, mock_set_state):
        self.manager.state.light_on = True
        self.manager.state.last_change_timestamp = 1000.0
        
        custom_time = datetime.fromtimestamp(2000.0, self.tz)
        duration = await self.manager.set_light_on(False, custom_time=custom_time)
        
        self.assertEqual(duration, 1000.0)
        self.assertFalse(self.manager.state.light_on)
        self.assertEqual(self.manager.state.last_change_timestamp, 2000.0)

if __name__ == '__main__':
    unittest.main()
