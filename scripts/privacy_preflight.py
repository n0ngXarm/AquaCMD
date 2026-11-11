#!/usr/bin/env python3
"""Run the same privacy guard used by the desktop source archive build."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'aqua-command-desktop/packaging/privacy_preflight.py'), run_name='__main__')
