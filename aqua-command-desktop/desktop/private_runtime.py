"""Private runtime inputs; this module performs no reads from industrial sources."""
import os
from pathlib import Path
from urllib.parse import quote


def catalog_path(config_dir=None):
    explicit = os.environ.get('AQUACMD_CATALOG_PATH')
    if explicit:
        return Path(explicit).expanduser()
    directory = Path(config_dir or Path.home() / '.config' / 'aqua-command')
    catalog = directory / 'catalog' / 'Export all.txt'
    return catalog if catalog.exists() else Path.home() / 'Downloads' / 'Export all.txt'


def redact_text(message, *credentials):
    text = str(message)
    variants = {variant for value in credentials if value
                for variant in (str(value), quote(str(value), safe=''))}
    for value in sorted(variants, key=len, reverse=True):
        text = text.replace(value, '[REDACTED]')
    return text
