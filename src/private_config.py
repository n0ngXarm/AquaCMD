"""Owner-only CLI configuration and credential-safe diagnostic formatting."""
import os
import io
import json
import re
from pathlib import Path
import stat
import tempfile
from urllib.parse import quote

from dotenv import dotenv_values, load_dotenv


def _private_path(path):
    path = Path(path).expanduser().absolute()
    if path.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise PermissionError('Private credentials must be stored outside the source repository')
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise PermissionError('Private configuration path cannot contain symlinks')
    return path


def private_env_path():
    explicit = os.environ.get('AQUACMD_ENV_FILE')
    if explicit:
        return _private_path(explicit)
    directory = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return _private_path(directory / 'aqua-command' / 'pwa.env')


def _regular_owned(path, *, private=False):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or (hasattr(os, 'getuid') and info.st_uid != os.getuid()):
        raise PermissionError('Configuration must be a regular file owned by this user')
    if private and os.name != 'nt' and info.st_mode & 0o077:
        raise PermissionError('Private configuration requires owner-only permissions')


def load_environment(legacy):
    """Explicit/private configuration takes priority; legacy input remains readable."""
    private = private_env_path()
    if private.exists() or private.is_symlink():
        _regular_owned(private, private=True)
        selected = private
    elif os.environ.get('AQUACMD_ENV_FILE'):
        selected = private  # An explicit missing profile never falls back to another one.
    else:
        selected = legacy
    if selected.exists() or selected.is_symlink():
        _regular_owned(selected)
        load_dotenv(selected, override=False)
    return private, selected


def redact_credentials(message, *values):
    text = re.sub(r'\b[0-9]{6,}:[A-Za-z0-9_-]{25,}', '[REDACTED]', str(message))
    variants = {variant for value in values if value
                for variant in (str(value), quote(str(value), safe=''))}
    for value in sorted(variants, key=len, reverse=True):
        text = text.replace(value, '[REDACTED]')
    return text


class PrivateConfigSaveError(OSError):
    def __init__(self, *, committed):
        super().__init__('Private configuration durability could not be confirmed' if committed
                         else 'Private configuration was not saved')
        self.committed = committed


def _atomic_private_write(path, content):
    if path.exists() or path.is_symlink():
        _regular_owned(path)
    descriptor, name = tempfile.mkstemp(prefix='.pwa-', dir=path.parent)
    temporary = Path(name)
    committed = False
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        committed = True
        if os.name != 'nt':
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
    except OSError:
        raise PrivateConfigSaveError(committed=committed) from None
    finally:
        temporary.unlink(missing_ok=True)


def save_environment(path, updates, *, source=None):
    """Preserve existing keys and an owner-only backup without deleting legacy input."""
    path = _private_path(path)
    if os.name == 'nt':
        raise PermissionError('Windows private CLI storage requires separately verified owner-only ACLs')
    source = path if path.exists() or path.is_symlink() else Path(source or path)
    original = b''
    values = {}
    if source.exists() or source.is_symlink():
        _regular_owned(source)
        original = source.read_bytes()
        values = dict(dotenv_values(stream=io.StringIO(original.decode('utf-8')), interpolate=False))
    values.update(updates)
    if any('\n' in str(value) or '\r' in str(value) for value in updates.values()):
        raise ValueError('Configuration values must be single-line text')
    if path.parent.is_symlink():
        raise PermissionError('Private configuration directory cannot be a symlink')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = path.parent.stat()
    if hasattr(os, 'getuid') and parent.st_uid != os.getuid():
        raise PermissionError('Private configuration directory must be owned by this user')
    if os.name != 'nt':
        path.parent.chmod(0o700)
    if original:
        _atomic_private_write(path.with_suffix('.env.bak'), original)
    lines = [key if value is None else f'{key}={json.dumps(str(value), ensure_ascii=False)}'
             for key, value in values.items()]
    _atomic_private_write(path, ('\n'.join(lines) + '\n').encode('utf-8'))
