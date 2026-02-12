import asyncio
import unittest
from network import NetworkMonitor

class TestNetworkIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_real_ping_success(self):
        # 100% working address (Google DNS)
        monitor = NetworkMonitor(on_light_on=None, on_light_off=None, host="8.8.8.8", port=53)
        success = await monitor.ping()
        print(f"\nReal ping to 8.8.8.8:53 -> {'SUCCESS' if success else 'FAILURE'}")
        self.assertTrue(success)

    async def test_real_ping_failure(self):
        # 100% non-working address (Reserved for documentation)
        monitor = NetworkMonitor(on_light_on=None, on_light_off=None, host="192.0.2.1", port=80)
        success = await monitor.ping()
        print(f"Real ping to 192.0.2.1:80 -> {'SUCCESS' if success else 'FAILURE'}")
        self.assertFalse(success)

if __name__ == '__main__':
    unittest.main()
