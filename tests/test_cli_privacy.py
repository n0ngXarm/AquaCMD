"""Credential-output and private-storage regressions. All credentials are synthetic."""
import contextlib
import io
import logging
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main as cli
from src.config import Config
from src.telegram_notifier import TelegramNotifier

TOKEN = 'unit-secret-sentinel'
CHAT = 'unit-recipient-sentinel'


class CredentialPrivacyTests(unittest.TestCase):
    def setup_profile(self, directory):
        legacy = directory / '.env'
        legacy.write_text('APP_ENV=lab\nCUSTOM_PRESERVE=value\n')
        private = directory / 'private' / 'pwa.env'
        return legacy, private

    def run_setup(self, directory, legacy, private):
        captured = []
        def ordinary_input(prompt):
            captured.append(prompt)
            return ''
        def secret_input(prompt):
            captured.append(prompt)
            return ''
        stream = io.StringIO()
        with patch.object(cli, 'BASE_DIR', directory), \
                patch.object(Config, 'TELEGRAM_BOT_TOKEN', TOKEN), \
                patch.object(Config, 'TELEGRAM_CHAT_ID', CHAT), \
                patch.object(Config, 'ENV_FILE', private, create=True), \
                patch.object(Config, 'ENV_SOURCE_FILE', legacy, create=True), \
                patch.object(cli, 'getpass', SimpleNamespace(getpass=secret_input, GetPassWarning=Warning), create=True), \
                patch('builtins.input', side_effect=ordinary_input), \
                contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            cli.cmd_setup()
        return stream.getvalue() + '\n'.join(captured)

    def test_setup_never_renders_stored_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            legacy, private = self.setup_profile(directory)
            output = self.run_setup(directory, legacy, private)
            self.assertFalse(TOKEN in output or CHAT in output, 'Credential appeared in setup output/prompt')

    def test_setup_migrates_without_overwriting_legacy_and_uses_private_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            legacy, private = self.setup_profile(directory)
            original = legacy.read_bytes()
            self.run_setup(directory, legacy, private)
            self.assertEqual(legacy.read_bytes(), original, 'Legacy configuration changed')
            self.assertTrue(private.is_file(), 'Private configuration was not created')
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)
            self.assertEqual(private.parent.stat().st_mode & 0o777, 0o700)
            self.assertIn('CUSTOM_PRESERVE', private.read_text())
            self.assertEqual(private.with_suffix('.env.bak').read_bytes(), original)

    def test_cli_status_never_renders_recipient_or_token(self):
        output = io.StringIO()
        with patch.object(Config, 'TELEGRAM_BOT_TOKEN', TOKEN), \
                patch.object(Config, 'TELEGRAM_CHAT_ID', CHAT), \
                patch.object(Config, 'APP_ENV', 'lab'), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            cli.cmd_test_telegram()
        self.assertFalse(TOKEN in output.getvalue() or CHAT in output.getvalue(), 'Credential appeared in CLI output')

    def test_transport_errors_cannot_expose_token_or_recipient(self):
        with patch.object(Config, 'TELEGRAM_CHAT_ID', CHAT):
            notifier = TelegramNotifier(bot_token=TOKEN)
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger('src.telegram_notifier')
        logger.addHandler(handler)
        try:
            with patch.object(Config, 'APP_ENV', 'production'), \
                    patch.object(Config, 'TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED', True), \
                    patch('urllib.request.urlopen', side_effect=urllib.error.URLError('request ' + TOKEN + ' ' + CHAT)):
                ok, message = notifier.test_connection()
                self.assertFalse(ok)
                self.assertFalse(notifier.send_message(CHAT, 'LAB'))
            output = message + stream.getvalue()
            self.assertFalse(TOKEN in output or CHAT in output, 'Credential appeared in error output')
        finally:
            logger.removeHandler(handler)


if __name__ == '__main__':
    unittest.main()
