"""Run the unchanged F3 handoff assertions with each initial theme (test-only)."""
import argparse
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--theme', choices=('light', 'dark'), required=True)
    args = parser.parse_args()
    if os.environ.get('AQUA_UX_TEST_PROFILE') != '1' or not str(Path.home()).startswith('/tmp/aqua-native-ux-'):
        raise SystemExit('Disposable UX test profile required')
    from desktop import f3_api_view
    f3_api_view.DEFAULT_THEME = args.theme
    sys.argv = [str(ROOT / 'tests/f3_handoff_native.py')]
    print('INITIAL_THEME=' + args.theme, flush=True)
    runpy.run_path(sys.argv[0], run_name='__main__')
