"""Unit and integration tests for PWA Water Notification System."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.database import Database
from src.pwa_client import PWAClient
from src.telegram_notifier import TelegramNotifier


class TestDatabase(unittest.TestCase):
    """Tests for SQLite database operations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_pwa.db"
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_outage(self):
        outage = {
            "branch_name": "ทดสอบสาขาเมือง",
            "title": "ท่อแตกฉุกเฉิน",
            "cause": "รถบรรทุกชนท่อ",
            "affected_area": "ถนนเทศบาล 1",
            "start_date": "2026-10-14 10:00:00",
            "end_date": "2026-10-14 14:00:00",
            "working_status_name": "กำลังดำเนินการ",
            "link": "https://pwa.co.th/test_outage_1",
            "contact": "02-123-4567"
        }

        # First insert should succeed
        inserted = self.db.save_outage(outage, initial_status="กำลังดำเนินการ")
        self.assertTrue(inserted)

        # Duplicate insert with same link should be rejected by unique constraint
        duplicate = self.db.save_outage(outage, initial_status="กำลังดำเนินการ")
        self.assertFalse(duplicate)

        # Retrieve and verify
        key = self.db.generate_alert_key(outage)
        rec = self.db.get_outage(key)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["branch_name"], "ทดสอบสาขาเมือง")
        self.assertEqual(rec["last_status_alerted"], "กำลังดำเนินการ")

        # Update status
        self.db.update_outage_status(key, "ดำเนินการแล้วเสร็จ")
        updated = self.db.get_outage(key)
        self.assertEqual(updated["working_status_name"], "ดำเนินการแล้วเสร็จ")
        self.assertEqual(updated["last_status_alerted"], "ดำเนินการแล้วเสร็จ")

    def test_subscriber_management(self):
        chat_id = "12345678"
        self.db.add_or_update_subscriber(chat_id, username="somchai", first_name="Somchai", branches=["ชลบุรี"])

        sub = self.db.get_subscriber(chat_id)
        self.assertIsNotNone(sub)
        self.assertEqual(sub["branches"], ["ชลบุรี"])
        self.assertEqual(sub["username"], "somchai")

        # Update branches
        self.db.add_or_update_subscriber(chat_id, branches=["เชียงใหม่", "พัทยา"])
        sub_updated = self.db.get_subscriber(chat_id)
        self.assertEqual(sub_updated["branches"], ["เชียงใหม่", "พัทยา"])

        # Active subscribers list
        active_subs = self.db.get_active_subscribers()
        self.assertEqual(len(active_subs), 1)

        # Deactivate
        self.db.set_subscriber_active(chat_id, False)
        self.assertEqual(len(self.db.get_active_subscribers()), 0)


class TestPWAClient(unittest.TestCase):
    """Tests for PWA Client parsing and quality checking logic."""

    def setUp(self):
        self.client = PWAClient()

    def test_branch_lookup(self):
        found = self.client.find_branch("เชียงใหม่")
        self.assertIsNotNone(found)
        self.assertEqual(found.get("code"), "1004")

        found_code = self.client.find_branch("1012")
        self.assertIsNotNone(found_code)
        self.assertIn("ลำพูน", found_code.get("name"))

    def test_quality_standards(self):
        # 1. Normal station
        normal_st = {
            "plantname": "สถานี ก",
            "pH": "7.2",
            "NTU": "1.2",
            "Cl": "0.8",
            "pic": "pass"
        }
        is_normal, issues = self.client.check_station_quality(normal_st)
        self.assertTrue(is_normal)
        self.assertEqual(len(issues), 0)

        # 2. Acidic pH and high turbidity
        bad_st = {
            "plantname": "สถานี ข",
            "pH": "5.5",
            "NTU": "8.5",
            "Cl": "0.1",
            "pic": "fail"
        }
        is_normal, issues = self.client.check_station_quality(bad_st)
        self.assertFalse(is_normal)
        self.assertTrue(any("pH" in i for i in issues))
        self.assertTrue(any("ความขุ่น" in i for i in issues))
        self.assertTrue(any("คลอรีน" in i for i in issues))


class TestTelegramNotifier(unittest.TestCase):
    """Tests for Telegram message formatting."""

    def test_outage_formatting(self):
        outage = {
            "branch_name": "ภูเก็ต",
            "title": "ล้างบ่อตกตะกอน",
            "cause": "บำรุงรักษาประจำปี",
            "affected_area": "ต.กะทู้ ทั้งตำบล",
            "start_date": "2026-10-15 08:00:00",
            "end_date": "2026-10-15 16:00:00",
            "working_status_name": "กำลังดำเนินการ",
            "contact": "076-123456",
            "link": "https://pwa.co.th/poster.jpg"
        }

        html_msg = TelegramNotifier.format_outage_message(outage)
        self.assertIn("ภูเก็ต", html_msg)
        self.assertIn("ล้างบ่อตกตะกอน", html_msg)
        self.assertIn("ต.กะทู้", html_msg)
        self.assertIn("กำลังดำเนินการ", html_msg)

        # Test update message
        outage["working_status_name"] = "ดำเนินการแล้วเสร็จ"
        update_msg = TelegramNotifier.format_outage_message(outage, is_update=True)
        self.assertIn("ดำเนินการแล้วเสร็จ", update_msg)


class TestMonitorServiceSecurity(unittest.TestCase):
    """Tests for REL-02: Notification Consent Enforcement and Delivery Authorization."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_silent_baseline_sync_no_startup_broadcast(self):
        """Verifies that cold start baseline sync is 100% silent and never dispatches Telegram messages."""
        from src.monitor_service import WaterMonitorService
        from unittest.mock import MagicMock

        fake_pwa = MagicMock()
        fake_pwa.get_all_active_outages.return_value = [
            {"id": 1, "branch_name": "เชียงใหม่", "working_status_name": "กำลังดำเนินการ"}
        ]
        fake_notifier = MagicMock()
        fake_notifier.default_chat_id = "12345678"

        service = WaterMonitorService(db=self.db, pwa=fake_pwa, notifier=fake_notifier)
        service.initialize_baseline()

        # Assert zero messages dispatched to Telegram during baseline sync
        fake_notifier.send_message.assert_not_called()
        self.assertTrue(service.is_initialized)
        self.assertEqual(self.db.count_outages(), 1)

    def test_decoupled_delivery_authorization_in_lab(self):
        """Verifies that in LAB environment, external network delivery is strictly blocked by default."""
        from src.telegram_notifier import TelegramNotifier
        from src.config import Config
        from unittest.mock import patch

        notifier = TelegramNotifier(bot_token="123456:FAKE_TOKEN_FOR_TESTING")

        with patch.object(Config, "APP_ENV", "lab"):
            self.assertFalse(notifier.is_delivery_authorized)

            # Test send_message produces zero network calls
            with patch("urllib.request.urlopen") as mock_urlopen:
                sent = notifier.send_message("12345", "Test Message")
                self.assertFalse(sent)
                mock_urlopen.assert_not_called()

            # Test send_photo produces zero network calls
            with patch("urllib.request.urlopen") as mock_urlopen:
                sent_photo = notifier.send_photo("12345", "http://example.com/p.jpg", "Caption")
                self.assertFalse(sent_photo)
                mock_urlopen.assert_not_called()

            # Test test_connection probe produces zero network calls
            with patch("urllib.request.urlopen") as mock_urlopen:
                ok, reason = notifier.test_connection()
                self.assertFalse(ok)
                self.assertIn("blocked in lab", reason)
                mock_urlopen.assert_not_called()

    def test_lab_env_cannot_bypass_consent_with_env_flag(self):
        """Negative test: Setting delivery auth flag cannot enable delivery if APP_ENV is lab."""
        from src.telegram_notifier import TelegramNotifier
        from src.config import Config

        notifier = TelegramNotifier(bot_token="123456:FAKE_TOKEN_FOR_TESTING", delivery_authorized=True)

        with patch.object(Config, "APP_ENV", "lab"):
            self.assertFalse(notifier.is_delivery_authorized, "LAB environment must unconditionally deny external delivery")

    def test_production_explicit_operator_consent(self):
        """Positive test: In production, delivery is enabled only with explicit operator consent."""
        from src.telegram_notifier import TelegramNotifier
        from src.config import Config

        # Without explicit consent -> False
        notifier_denied = TelegramNotifier(bot_token="123456:FAKE_TOKEN_FOR_TESTING", delivery_authorized=False)
        with patch.object(Config, "APP_ENV", "production"):
            self.assertFalse(notifier_denied.is_delivery_authorized)

        # With explicit consent -> True
        notifier_approved = TelegramNotifier(bot_token="123456:FAKE_TOKEN_FOR_TESTING", delivery_authorized=True)
        with patch.object(Config, "APP_ENV", "production"):
            self.assertTrue(notifier_approved.is_delivery_authorized)

    def test_bot_polling_zero_egress_in_lab(self):
        """Zero-egress test: Bot polling and getUpdates must make 0 network requests in LAB."""
        from src.telegram_bot import TelegramBot
        from src.telegram_notifier import TelegramNotifier
        from src.config import Config

        notifier = TelegramNotifier(bot_token="123456:FAKE_TOKEN_FOR_TESTING")
        bot = TelegramBot(db=MagicMock(), pwa=MagicMock(), notifier=notifier)

        with patch.object(Config, "APP_ENV", "lab"):
            self.assertFalse(bot.is_polling_authorized)

            # Assert getUpdates produces zero network calls
            with patch("urllib.request.urlopen") as mock_urlopen:
                updates = bot._get_updates(offset=0, timeout=1)
                self.assertEqual(updates, [])
                mock_urlopen.assert_not_called()

            # Assert start_polling exits immediately without polling loop
            with patch("urllib.request.urlopen") as mock_urlopen:
                bot.start_polling()
                self.assertFalse(bot.is_running)
                mock_urlopen.assert_not_called()

    def test_decoupled_permissions_independent_gates(self):
        """Verifies that delivery authorization and polling authorization are strictly decoupled."""
        from src.telegram_bot import TelegramBot
        from src.telegram_notifier import TelegramNotifier
        from src.config import Config

        notifier = TelegramNotifier(bot_token="123456:FAKE_TOKEN_FOR_TESTING", delivery_authorized=True)
        bot = TelegramBot(db=MagicMock(), pwa=MagicMock(), notifier=notifier, polling_authorized=False)

        with patch.object(Config, "APP_ENV", "production"):
            # Delivery authorized, but polling NOT authorized
            self.assertTrue(notifier.is_delivery_authorized)
            self.assertFalse(bot.is_polling_authorized)

            # Polling authorized, but delivery NOT authorized
            notifier_no_deliv = TelegramNotifier(bot_token="123456:FAKE_TOKEN_FOR_TESTING", delivery_authorized=False)
            bot_poll_auth = TelegramBot(db=MagicMock(), pwa=MagicMock(), notifier=notifier_no_deliv, polling_authorized=True)
            self.assertFalse(notifier_no_deliv.is_delivery_authorized)
            self.assertTrue(bot_poll_auth.is_polling_authorized)

    def test_main_cmd_test_telegram_zero_egress_in_lab(self):
        """Verifies that main.py cmd_test_telegram makes zero network calls in LAB."""
        import io
        import sys
        from unittest.mock import patch
        import main

        with patch.object(main.Config, "APP_ENV", "lab"):
            with patch("urllib.request.urlopen") as mock_urlopen:
                captured_out = io.StringIO()
                with patch("sys.stdout", captured_out):
                    main.cmd_test_telegram()
                mock_urlopen.assert_not_called()
                output = captured_out.getvalue()
                self.assertIn("REL-02", output)
                self.assertIn("ระงับตามนโยบายความปลอดภัย", output)

    def test_strict_production_allowlist_negative_environments(self):
        """Negative test: Strict allowlist default-deny for non-production environments."""
        from src.telegram_bot import TelegramBot
        from src.telegram_notifier import TelegramNotifier
        from src.config import Config

        invalid_environments = [
            "staging",
            "qa",
            "unknown",
            "",
            "   ",
            "production_test",
            "prod",
            "dev",
            "test",
            "malformed!env"
        ]

        for env in invalid_environments:
            with patch.object(Config, "APP_ENV", env):
                # Constructor override must NOT enable egress in non-production
                notifier = TelegramNotifier(bot_token="123456:FAKE_TOKEN_FOR_TESTING", delivery_authorized=True)
                self.assertFalse(
                    notifier.is_delivery_authorized,
                    f"Environment '{env}' must be denied outbound delivery even with constructor override"
                )

                # Inbound polling must also be strictly denied
                bot = TelegramBot(db=MagicMock(), pwa=MagicMock(), notifier=notifier, polling_authorized=True)
                self.assertFalse(
                    bot.is_polling_authorized,
                    f"Environment '{env}' must be denied inbound polling even with constructor override"
                )

                # Zero network requests on probe/send
                with patch("urllib.request.urlopen") as mock_urlopen:
                    self.assertFalse(notifier.send_message("123", "Test"))
                    self.assertEqual(bot._get_updates(), [])
                    mock_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
