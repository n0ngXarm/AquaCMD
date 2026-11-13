"""Check for undefined names across desktop/*.py using pyflakes when available.

Runs pyflakes over all Python modules in desktop/ and flags only UndefinedName
errors, skipping unused imports and variables. If pyflakes is not installed,
the test is skipped gracefully.
"""
from pathlib import Path
import unittest

DESKTOP = Path(__file__).resolve().parents[1]


class UndefinedNamesTests(unittest.TestCase):
    def test_no_undefined_names_in_desktop_modules(self):
        try:
            from pyflakes import api, reporter, messages
        except ImportError:
            self.skipTest("pyflakes is not installed")

        undefined_errors = []
        for file in sorted(DESKTOP.glob("*.py")):
            code = file.read_text(encoding="utf-8")

            class CustomReporter(reporter.Reporter):
                def __init__(self):
                    self.messages = []

                def unexpectedError(self, filename, msg):
                    self.messages.append((filename, f"Unexpected error: {msg}"))

                def syntaxError(self, filename, msg, lineno, offset, text):
                    self.messages.append((filename, f"Syntax error at line {lineno}: {msg}"))

                def flake(self, msg):
                    if isinstance(msg, messages.UndefinedName):
                        self.messages.append((msg.filename, f"{msg.message} (line {msg.lineno})"))

            rep = CustomReporter()
            api.check(code, file.name, rep)
            if rep.messages:
                undefined_errors.extend(rep.messages)

        self.assertEqual(undefined_errors, [], f"Undefined names detected: {undefined_errors}")


if __name__ == "__main__":
    unittest.main()
