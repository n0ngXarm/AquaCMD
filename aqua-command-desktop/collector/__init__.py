"""Expose the src-layout collector to `python -m collector.probe_once`."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / 'src' / 'collector')]
