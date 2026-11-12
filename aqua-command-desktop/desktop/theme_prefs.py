"""The single presentation preference; no operational settings are read or written."""
import json
import os
from pathlib import Path
import tempfile

try:
    from .theme_tokens import DEFAULT_THEME, THEMES
except ImportError:
    from theme_tokens import DEFAULT_THEME, THEMES


def load_theme(directory):
    try:
        path = Path(directory) / 'ui_prefs.json'
        if path.is_symlink() or path.stat().st_size > 128:
            return DEFAULT_THEME
        value = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(value, dict) and set(value) == {'theme'} and value['theme'] in THEMES:
            return value['theme']
    except (OSError, ValueError, TypeError):
        pass
    return DEFAULT_THEME


def save_theme(directory, mode):
    if mode not in THEMES:
        raise ValueError('Unsupported presentation theme')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.ui_prefs-', dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({'theme': mode}, stream, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / 'ui_prefs.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
