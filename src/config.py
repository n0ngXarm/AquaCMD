"""Configuration management for PWA Water Notification System."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")


class Config:
    """Application configuration."""

    # Telegram Bot Settings
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    # Monitoring Settings
    CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))
    ENABLE_OUTAGE_ALERT = os.getenv("ENABLE_OUTAGE_ALERT", "true").lower() in ("true", "1", "yes")
    ENABLE_QUALITY_ALERT = os.getenv("ENABLE_QUALITY_ALERT", "true").lower() in ("true", "1", "yes")
    # Environment & Deployment Mode (Strict Default-Deny Allowlist)
    APP_ENV = os.getenv("APP_ENV", "lab").strip().lower()

    # External Notification Delivery Authorization Gate (REL-02)
    # Default-deny: APP_ENV must be strictly "production".
    # Any other environment (lab, staging, qa, dev, test, unknown, empty, malformed) is denied.
    _DELIVERY_AUTH_RAW = os.getenv("TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED", "false").strip().lower()
    TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED = (
        APP_ENV == "production" and _DELIVERY_AUTH_RAW in ("true", "1", "yes")
    )

    # Inbound Telegram Command Polling Authorization Gate (REL-02)
    # Decoupled from outbound delivery authorization.
    # Default-deny: APP_ENV must be strictly "production".
    # Any other environment (lab, staging, qa, dev, test, unknown, empty, malformed) is denied.
    _POLLING_AUTH_RAW = os.getenv("TELEGRAM_INBOUND_POLLING_AUTHORIZED", "false").strip().lower()
    TELEGRAM_INBOUND_POLLING_AUTHORIZED = (
        APP_ENV == "production" and _POLLING_AUTH_RAW in ("true", "1", "yes")
    )

    # Quality alert threshold settings (PWA drinking water standard)
    PH_MIN = float(os.getenv("PH_MIN", "6.5"))
    PH_MAX = float(os.getenv("PH_MAX", "8.5"))
    NTU_MAX = float(os.getenv("NTU_MAX", "5.0"))
    CL_MIN = float(os.getenv("CL_MIN", "0.2"))
    CL_MAX = float(os.getenv("CL_MAX", "2.0"))

    # Cooldown for quality alerts (hours) to prevent repeated alerts for the same station
    QUALITY_ALERT_COOLDOWN_HOURS = int(os.getenv("QUALITY_ALERT_COOLDOWN_HOURS", "6"))

    # Monitored branches: comma-separated list of branch names or codes.
    # Empty string or '*' means monitor ALL branches across Thailand.
    _MONITOR_BRANCHES_RAW = os.getenv("MONITOR_BRANCHES", "*").strip()

    # Storage paths
    DATA_DIR = BASE_DIR / "data"
    DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "pwa_alerts.db")))

    @classmethod
    def get_monitored_branches(cls) -> list[str]:
        """Returns list of monitored branch names or empty list if monitoring all."""
        raw = cls._MONITOR_BRANCHES_RAW
        if not raw or raw == "*":
            return []
        return [b.strip() for b in raw.split(",") if b.strip()]

    @classmethod
    def is_branch_monitored(cls, branch_name: str) -> bool:
        """Checks if a branch is in the monitored list."""
        monitored = cls.get_monitored_branches()
        if not monitored:
            return True  # All branches monitored
        for b in monitored:
            if b.lower() in branch_name.lower():
                return True
        return False

    @classmethod
    def is_telegram_configured(cls) -> bool:
        """Checks if Telegram bot token is configured."""
        return bool(cls.TELEGRAM_BOT_TOKEN)
