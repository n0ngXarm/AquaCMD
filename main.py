"""Unified entry point for PWA Water Notification System.
ระบบแจ้งเตือนน้ำประปาส่วนภูมิภาค (กปภ.) ไปยัง Telegram
"""

import argparse
import getpass
import warnings
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from src.config import BASE_DIR, Config
from src.private_config import save_environment, PrivateConfigSaveError
from src.database import Database
from src.monitor_service import WaterMonitorService
from src.pwa_client import PWAClient
from src.telegram_bot import TelegramBot
from src.telegram_notifier import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("PWA_WaterSystem")


def cmd_test_fetch() -> None:
    """Tests fetching live data from PWA without sending Telegram messages."""
    print("=" * 60)
    print("💧 ทดสอบการดึงข้อมูลสดจากการประปาส่วนภูมิภาค (กปภ.)")
    print("=" * 60)

    client = PWAClient()

    # 1. Test Outage API
    print("\n[1/2] กำลังทดสอบดึงข้อมูลประกาศหยุดจ่ายน้ำ (PWA Outage API)...")
    outages = client.get_all_active_outages(limit=10)
    print(f"✅ ดึงข้อมูลสำเร็จ! พบประกาศที่กำลังเผยแพร่: {len(outages)} รายการ (สุ่มแสดง 3 รายการล่าสุด):")
    for idx, item in enumerate(outages[:3], 1):
        print(f"\n  --- รายการที่ {idx} ---")
        print(f"  🏢 สาขา: กปภ.สาขา {item.get('branch_name')}")
        print(f"  📌 หัวข้อ: {item.get('title')}")
        print(f"  ⚙️ สาเหตุ: {item.get('cause')}")
        print(f"  📍 พื้นที่: {item.get('affected_area')[:100]}...")
        print(f"  ⏱️ ระยะเวลา: {item.get('start_date')} ถึง {item.get('end_date')}")
        print(f"  📊 สถานะ: {item.get('working_status_name')}")
        print(f"  🖼️ โปสเตอร์: {item.get('link')}")

    # 2. Test RTU Water Quality
    print("\n[2/2] กำลังทดสอบดึงข้อมูลตรวจวัดคุณภาพน้ำประปา RTU (Sensors)...")
    stations = client.fetch_rtu_water_quality()
    print(f"✅ ดึงข้อมูลสำเร็จ! พบสถานีตรวจวัดทั้งหมด: {len(stations)} สถานี")

    # Sample standard analysis
    passed = [s for s in stations.values() if s.get("pic") == "pass"]
    failed = [s for s in stations.values() if s.get("pic") != "pass"]
    print(f"  🟢 สถานีผ่านเกณฑ์: {len(passed)} สถานี")
    print(f"  🔴 สถานีไม่ผ่านเกณฑ์ / ค่าเบี่ยงเบน: {len(failed)} สถานี")

    if failed:
        print("\n  ตัวอย่างสถานีที่ไม่ผ่านเกณฑ์มาตรฐาน กปภ.:")
        for s in failed[:3]:
            is_normal, issues = client.check_station_quality(s)
            print(f"  - {s.get('plantname')} (สังกัด: {s.get('wwcode_name') or s.get('divisionname')})")
            print(f"    pH: {s.get('pH')} | NTU: {s.get('NTU')} | Cl: {s.get('Cl')} | Issues: {', '.join(issues)}")

    print("\n" + "=" * 60)
    print("✨ การทดสอบดึงข้อมูลจาก กปภ. เสร็จสมบูรณ์ ข้อมูลพร้อมใช้งาน 100%!")
    print("=" * 60)


def cmd_test_telegram() -> None:
    """Tests sending a sample notification to configured Telegram Chat ID."""
    print("=" * 60)
    print("📲 ทดสอบการเชื่อมต่อและส่งข้อความไปยัง Telegram")
    print("=" * 60)

    notifier = TelegramNotifier()

    print(f"Bot Token: {'ตั้งค่าแล้ว (ความยาว ' + str(len(Config.TELEGRAM_BOT_TOKEN)) + ' ตัวอักษร)' if Config.is_telegram_configured() else '❌ ยังไม่ได้ตั้งค่า'}")
    print("Target Chat ID: " + ("[REDACTED]" if Config.TELEGRAM_CHAT_ID else "ยังไม่ได้ตั้งค่า"))

    if not notifier.is_delivery_authorized:
        print(f"\n🛑 การเชื่อมต่อไปยัง Telegram API ถูกระงับตามนโยบายความปลอดภัย (REL-02): APP_ENV='{Config.APP_ENV}'")
        print("💡 ในโหมด LAB/Non-production ห้ามส่ง HTTP Request (getMe, sendMessage) ออกภายนอก")
        print("💡 ต้องใช้ APP_ENV='production' และ TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED=true เท่านั้น")
        return

    ok, msg = notifier.test_connection()
    if not ok:
        print(f"\n❌ การเชื่อมต่อล้มเหลว: {msg}")
        print("💡 กรุณาตรวจสอบ TELEGRAM_BOT_TOKEN ในไฟล์ .env")
        return

    print(f"\n✅ {msg}")

    if not Config.TELEGRAM_CHAT_ID:
        print("\n⚠️ ยังไม่ได้ระบุ TELEGRAM_CHAT_ID ในไฟล์ .env")
        print("💡 คุณสามารถรับ Chat ID ได้โดยการทักบอท @userinfobot บน Telegram แล้วนำ ID มาใส่ใน .env")
        return

    print("\nกำลังส่งข้อความทดสอบไปยังผู้รับที่ตั้งค่าไว้...")
    test_text = (
        "💧 <b>[ทดสอบระบบแจ้งเตือนน้ำประปาส่วนภูมิภาค]</b>\n"
        "──────────────────\n"
        "✅ บอทแจ้งเตือนของคุณเชื่อมต่อกับระบบสำเร็จเรียบร้อยแล้ว!\n\n"
        "พร้อมรับการแจ้งเตือนเมื่อมี:\n"
        " • 🚨 ประกาศหยุดจ่ายน้ำ / ท่อแตกฉุกเฉิน / ซ่อมท่อ\n"
        " • 🟢 อัปเดตเมื่อซ่อมเสร็จและน้ำเริ่มกลับมาไหลปกติ\n"
        " • 🧪 แจ้งเตือนเมื่อคุณภาพน้ำประปา RTU ผิดเกณฑ์มาตรฐาน\n"
        "──────────────────\n"
        "🔔 <i>PWA Water Alert System</i>"
    )

    sent = notifier.send_message(Config.TELEGRAM_CHAT_ID, test_text)
    if sent:
        print("🎉 ส่งข้อความสำเร็จ! กรุณาตรวจสอบแอปพลิเคชัน Telegram ของคุณ")
    else:
        print("❌ การส่งข้อความล้มเหลว กรุณาตรวจสอบว่าคุณได้กด 'Start' แชทกับบอทแล้วหรือยัง")


def cmd_setup() -> None:
    """Interactive wizard to configure .env settings."""
    env_file = Config.ENV_FILE
    print("ตั้งค่า private configuration ของ AQUA COMMAND")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            token = getpass.getpass("Telegram Bot Token [ตั้งค่าแล้ว, เว้นว่างเพื่อคงค่าเดิม]: ").strip()
            chat_id = getpass.getpass("Telegram Chat ID [เว้นว่างเพื่อคงค่าเดิม]: ").strip()
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        print("Secure credential input unavailable. Configuration was not changed.", file=sys.stderr)
        raise SystemExit(1) from None
    branches = input("สาขาที่ติดตาม [*]: ").strip() or "*"
    interval = input("รอบตรวจข้อมูล วินาที [300]: ").strip() or "300"
    try:
        if int(interval) <= 0:
            raise ValueError()
        updates = {
            'TELEGRAM_BOT_TOKEN': token or Config.TELEGRAM_BOT_TOKEN,
            'TELEGRAM_CHAT_ID': chat_id or Config.TELEGRAM_CHAT_ID,
            'MONITOR_BRANCHES': branches,
            'CHECK_INTERVAL_SECONDS': interval,
        }
        save_environment(env_file, updates, source=Config.ENV_SOURCE_FILE)
    except PrivateConfigSaveError as error:
        print("Configuration saved but durability is unconfirmed." if error.committed
              else "Private configuration was not saved.", file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError):
        print("Private configuration could not be saved. Check the profile and input.", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"บันทึก private configuration แล้วที่ {env_file}")


def cmd_run(mode: str = "all") -> None:
    """Runs the water alert system (monitor, bot, or both)."""
    db = Database()
    pwa = PWAClient()
    notifier = TelegramNotifier()

    if not notifier.is_configured:
        logger.warning("=" * 60)
        logger.warning("⚠️ คำเตือน: ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN ในไฟล์ .env")
        logger.warning("คุณสามารถรัน 'python main.py setup' เพื่อตั้งค่า หรือกรอกใน .env ได้เลย")
        logger.warning("=" * 60)

    monitor = WaterMonitorService(db=db, pwa=pwa, notifier=notifier)
    bot = TelegramBot(db=db, pwa=pwa, notifier=notifier)

    threads: list[threading.Thread] = []

    def handle_exit(sig, frame):
        logger.info("Shutdown signal received. Stopping services...")
        monitor.stop()
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    if mode in ("all", "monitor"):
        t_monitor = threading.Thread(target=monitor.run_loop, name="PWA-MonitorThread", daemon=True)
        t_monitor.start()
        threads.append(t_monitor)
        logger.info("Background PWA Monitor service started.")

    if mode in ("all", "bot"):
        if not bot.is_polling_authorized:
            logger.warning(
                "Interactive Telegram Bot polling skipped: APP_ENV='%s' (polling authorization not granted). "
                "Network policy prohibits bot polling thread in non-production.",
                Config.APP_ENV
            )
        elif notifier.is_configured:
            t_bot = threading.Thread(target=bot.start_polling, name="PWA-BotThread", daemon=True)
            t_bot.start()
            threads.append(t_bot)
            logger.info("Interactive Telegram Bot polling started.")
        else:
            logger.warning("Telegram Bot polling skipped because Bot Token is not configured.")

    logger.info("System is active. Press Ctrl+C to terminate.")

    # Keep main thread alive
    try:
        while True:
            signal.pause()
    except (KeyboardInterrupt, SystemExit, AttributeError):
        import time
        while True:
            time.sleep(1)


def main() -> None:
    """CLI Argument parser."""
    parser = argparse.ArgumentParser(
        description="ระบบแจ้งเตือนน้ำประปาส่วนภูมิภาค (กปภ.) ไปยัง Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "command",
        choices=["run", "monitor", "bot", "test-fetch", "test-telegram", "setup"],
        nargs="?",
        default="run",
        help="คำสั่งที่ต้องการทำงาน (default: run)"
    )

    args = parser.parse_args()

    if args.command == "test-fetch":
        cmd_test_fetch()
    elif args.command == "test-telegram":
        cmd_test_telegram()
    elif args.command == "setup":
        cmd_setup()
    elif args.command == "monitor":
        cmd_run("monitor")
    elif args.command == "bot":
        cmd_run("bot")
    elif args.command == "run":
        cmd_run("all")


if __name__ == "__main__":
    main()
