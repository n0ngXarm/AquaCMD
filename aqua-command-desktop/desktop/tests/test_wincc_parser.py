"""Tests for Siemens WinCC V8.1 Tag Management Export parser (33 columns)."""
from pathlib import Path
import tempfile
import unittest

from app import scan_wincc_tags

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPORT_PATH = REPO_ROOT / 'docs' / 'tags' / 'Export all.txt'


class TestWinCCExportParser(unittest.TestCase):
    def test_parse_real_export_file(self):
        self.assertTrue(EXPORT_PATH.exists(), f"Real export file must exist at {EXPORT_PATH}")
        tags = scan_wincc_tags(EXPORT_PATH)
        self.assertEqual(len(tags), 457, "Must discover exactly 457 tags")

        groups = {t['group'] for t in tags}
        self.assertEqual(len(groups), 10, "Must discover exactly 10 plant groups")
        self.assertIn('High_VSD', groups)
        self.assertIn('High_Valve', groups)
        self.assertIn('High1_PT1PT', groups)
        self.assertIn('Default', groups)

        first = tags[0]
        self.assertEqual(first['name'], 'BVEC1PT.AUTO_C')
        self.assertEqual(first['type'], 'Binary Tag')
        self.assertEqual(first['group'], 'High_Valve')
        self.assertEqual(first['addr'], 'DB62,D108.3')

        raw = first['raw_metadata']
        self.assertGreaterEqual(len(raw), 33, "Raw metadata must preserve all 33 columns")
        self.assertIn('Linear scaling', raw)
        self.assertIn('OPC write protection', raw)
        self.assertIn('WinCC Cloud', raw)
        self.assertIn('[NAME][100][1]', raw)
        self.assertIn('[ADDRPARAMS][108][1]', raw)

    def test_parse_utf8_bom_odd_and_even_lengths(self):
        template = (
            "DmTag\tTags\tTag\r\n"
            "[NAME][100][1]\t[COMMENT][211][1]\t[TYPE][101][1]\t[LENGTH][105][1]\t[FORMAT][106][1]\t[CONNECTION][102][1]\t[GROUP][104][1]\t[ADDRPARAMS][108][1]\r\n"
            "Name\tComment\tData type\tLength\tFormat adaptation\tConnection\tGroup\tAddress\r\n"
            "TEST_BOM.PV\t{padding}\tFloat\t4\t\tS7_1\tHigh_VSD\tDB1,DBD0\r\n"
        )

        for pad_char in ('A', 'AB'):  # Creates different total byte lengths
            content_str = template.format(padding=pad_char)
            raw_bytes = b'\xef\xbb\xbf' + content_str.encode('utf-8')
            is_even = len(raw_bytes) % 2 == 0

            with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
                f.write(raw_bytes)
                path = Path(f.name)

            try:
                tags = scan_wincc_tags(path)
                self.assertEqual(len(tags), 1, f"Failed on {'even' if is_even else 'odd'} length UTF-8 BOM file")
                self.assertEqual(tags[0]['name'], 'TEST_BOM.PV')
                self.assertEqual(tags[0]['group'], 'High_VSD')
                self.assertEqual(tags[0]['comment'], pad_char)
            finally:
                if path.exists():
                    path.unlink()

    def test_parse_utf16_le_bom(self):
        content = (
            "DmTag\tTags\tTag\r\n"
            "[NAME][100][1]\t[COMMENT][211][1]\t[TYPE][101][1]\t[LENGTH][105][1]\t[FORMAT][106][1]\t[CONNECTION][102][1]\t[GROUP][104][1]\t[ADDRPARAMS][108][1]\r\n"
            "Name\tComment\tData type\tLength\tFormat adaptation\tConnection\tGroup\tAddress\r\n"
            "UTF16_TAG\tTest UTF-16\tBinary Tag\t1\t\tS7_CONN\tHigh_Valve\tDB10,D0.0\r\n"
        )
        raw_bytes = b'\xff\xfe' + content.encode('utf-16-le')
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(raw_bytes)
            path = Path(f.name)

        try:
            tags = scan_wincc_tags(path)
            self.assertEqual(len(tags), 1)
            self.assertEqual(tags[0]['name'], 'UTF16_TAG')
            self.assertEqual(tags[0]['type'], 'Binary Tag')
            self.assertEqual(tags[0]['group'], 'High_Valve')
            self.assertEqual(tags[0]['addr'], 'DB10,D0.0')
        finally:
            if path.exists():
                path.unlink()

    def test_parse_column_mismatch_and_incomplete_rows(self):
        content = (
            "DmTag\tTags\tTag\r\n"
            "[NAME][100][1]\t[COMMENT][211][1]\t[TYPE][101][1]\t[LENGTH][105][1]\t[FORMAT][106][1]\t[CONNECTION][102][1]\t[GROUP][104][1]\t[ADDRPARAMS][108][1]\r\n"
            "Name\tComment\tData type\tLength\tFormat adaptation\tConnection\tGroup\tAddress\r\n"
            "SHORT_ROW\tOnlyTwoCols\r\n"
            "FULL_ROW\tComment\tWord\t2\t\tCONN\tHigh1_PT1PT\tDB3,DBW0\textra1\textra2\r\n"
            "\r\n"
            "\t\t\t\r\n"  # Empty tabs
        )
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(content.encode('utf-8'))
            path = Path(f.name)

        try:
            tags = scan_wincc_tags(path)
            self.assertEqual(len(tags), 2, "Parser must handle short and long rows without crashing")
            self.assertEqual(tags[0]['name'], 'SHORT_ROW')
            self.assertEqual(tags[0]['comment'], 'OnlyTwoCols')
            self.assertEqual(tags[0]['group'], 'Default')  # Fallback to Default
            self.assertEqual(tags[0]['addr'], 'Internal')  # Fallback to Internal

            self.assertEqual(tags[1]['name'], 'FULL_ROW')
            self.assertEqual(tags[1]['group'], 'High1_PT1PT')
        finally:
            if path.exists():
                path.unlink()

    def test_parse_empty_and_non_existent(self):
        self.assertEqual(scan_wincc_tags(Path('/non/existent/path.txt')), [])
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            path = Path(f.name)
        try:
            self.assertEqual(scan_wincc_tags(path), [])
        finally:
            if path.exists():
                path.unlink()


if __name__ == '__main__':
    unittest.main()
