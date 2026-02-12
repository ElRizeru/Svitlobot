import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

TARGET_IP: str = os.getenv("TARGET_IP", "")
TARGET_PORT: int = 8443
PING_INTERVAL: int = 10
PING_TIMEOUT: int = 5
PING_TIMEOUT_THRESHOLD: int = 120

TUYA_DEVICE_ID: str = os.getenv("TUYA_DEVICE_ID", "")
TUYA_ACCESS_ID: str = os.getenv("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET: str = os.getenv("TUYA_ACCESS_SECRET", "")
TUYA_REGION: str = "eu"

GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO: str = "Baskerville42/outage-data-ua"
GITHUB_IMAGE_PATH: str = "images/kyiv-region/gpv-6-2-emergency.png"
GITHUB_JSON_PATH: str = "data/kyiv-region.json"

SCHEDULE_GROUP: str = "GPV6.2"
SCHEDULE_FETCH_INTERVAL: int = 120

TIMEZONE: str = "Europe/Kyiv"
