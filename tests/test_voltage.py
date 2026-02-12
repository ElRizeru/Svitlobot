import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
from voltage import VoltageMonitor, get_voltage_stats, generate_voltage_chart
from config import TIMEZONE

class TestVoltageMonitor(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.monitor = VoltageMonitor(interval=1)
        self.tz = ZoneInfo(TIMEZONE)

    @patch('voltage.tinytuya.Cloud')
    def test_fetch_voltage_sync_success(self, mock_cloud_class):
        mock_cloud = MagicMock()
        mock_cloud_class.return_value = mock_cloud
        mock_cloud.getstatus.return_value = {
            "result": [
                {"code": "cur_voltage", "value": 2250}
            ]
        }
        
        voltage = self.monitor._fetch_voltage_sync()
        self.assertEqual(voltage, 225.0)

    @patch('voltage.tinytuya.Cloud')
    def test_fetch_voltage_sync_fail(self, mock_cloud_class):
        mock_cloud = MagicMock()
        mock_cloud_class.return_value = mock_cloud
        mock_cloud.getstatus.return_value = {"error": "failed"}
        
        voltage = self.monitor._fetch_voltage_sync()
        self.assertIsNone(voltage)

    @patch('voltage.db_manager', new_callable=MagicMock)
    async def test_get_voltage_stats(self, mock_db):
        mock_conn = AsyncMock()
        mock_db.conn = mock_conn
        mock_cursor = AsyncMock()
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (210.0, 235.0, 222.5)
        
        min_v, max_v, avg_v = await get_voltage_stats()
        
        self.assertEqual(min_v, 210.0)
        self.assertEqual(max_v, 235.0)
        self.assertEqual(avg_v, 222.5)

    @patch('voltage.db_manager', new_callable=MagicMock)
    async def test_generate_voltage_chart(self, mock_db):
        mock_conn = AsyncMock()
        mock_db.conn = mock_conn
        mock_cursor = AsyncMock()
        mock_conn.execute.return_value = mock_cursor
        
        mock_cursor.fetchall.return_value = [
            (220.0, 1770760800.0),
            (225.0, 1770764400.0)
        ]
        
        chart_bytes = await generate_voltage_chart(hours=24)
        
        self.assertIsNotNone(chart_bytes)
        self.assertIsInstance(chart_bytes, bytes)
        self.assertTrue(len(chart_bytes) > 0)
        self.assertEqual(chart_bytes[:8], b'\x89PNG\r\n\x1a\n')

if __name__ == '__main__':
    unittest.main()
