import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from network import NetworkMonitor
from config import TIMEZONE, PING_TIMEOUT_THRESHOLD

class TestNetworkMonitor(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.on_light_on = AsyncMock()
        self.on_light_off = AsyncMock()
        self.monitor = NetworkMonitor(
            on_light_on=self.on_light_on,
            on_light_off=self.on_light_off,
            initial_state=True
        )

    @patch('asyncio.open_connection', new_callable=AsyncMock)
    async def test_ping_success(self, mock_open_connection):
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (AsyncMock(), mock_writer)
        
        success = await self.monitor.ping()
        self.assertTrue(success)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()

    @patch('asyncio.open_connection', side_effect=asyncio.TimeoutError)
    async def test_ping_failure(self, mock_open_connection):
        success = await self.monitor.ping()
        self.assertFalse(success)

    @patch.object(NetworkMonitor, 'ping', new_callable=AsyncMock)
    async def test_check_hysteresis(self, mock_ping):
        mock_ping.return_value = False
        
        await self.monitor.check(100.0)
        self.assertTrue(self.monitor.current_state)
        self.on_light_off.assert_not_called()
        
        with patch('network.datetime') as mock_datetime:
            mock_now = datetime.now(ZoneInfo(TIMEZONE))
            mock_datetime.now.return_value = mock_now + timedelta(seconds=PING_TIMEOUT_THRESHOLD + 1)
            
            self.monitor.first_failure_time = mock_now
            
            await self.monitor.check(100.0)
            
            self.assertFalse(self.monitor.current_state)
            self.on_light_off.assert_called_once()

    @patch.object(NetworkMonitor, 'ping', new_callable=AsyncMock)
    async def test_check_restore(self, mock_ping):
        self.monitor.current_state = False
        mock_ping.return_value = True
        
        await self.monitor.check(100.0)
        
        self.assertTrue(self.monitor.current_state)
        self.on_light_on.assert_called_once()

if __name__ == '__main__':
    unittest.main()
