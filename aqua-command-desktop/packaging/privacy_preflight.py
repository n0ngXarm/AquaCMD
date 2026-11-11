#!/usr/bin/env python3
"""Scan current/index text without printing matching private values. History is separate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CREDENTIAL = re.compile(r'\b\d{6,}:[A-Za-z0-9_-]{25,}|\bgh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,}|\b(?:AKIA|ASIA)[A-Z0-9]{16}')
HOME = re.compile('/' + r'(?:home|Users)/[A-Za-z0-9_.-]+/')
KEY = re.compile('-----BEGIN ' + r'(?:[A-Z0-9]+ )*PRIVATE KEY-----')
REVIEWED_FONTS = {
    'IBMPlexMono-Medium.woff2': '01d285447409c8a588692162439a038b8cbd7871309ee20267b0d2d91c6e8e22',
    'IBMPlexMono-Regular.woff2': '08949f728dc52d528e69b1667d15c89a5686a4ee9a296ff90983985f99c380f7',
    'IBMPlexSansThai-Medium.woff2': '7e01c133031aba4ca902d81930096f0224d83f808014c1232016b49e0a7ecff6',
    'IBMPlexSansThai-Regular.woff2': '2d66381c26d32bf2a95bfe559d1a5ed5475fcdac3fa128e45a33301010d42056',
    'IBMPlexSansThai-SemiBold.woff2': 'ea935955dc3bccb684f8fb772dbd429250dd0d3dfee9483995a3ee3456471df8',
}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def private_names(path):
    if path is None:
        return None
    data = path.read_bytes()
    text = data.decode('utf-16') if data.startswith((b'\xff\xfe', b'\xfe\xff')) else data.decode('utf-8-sig')
    names = {line.split('\t')[0].strip() for line in text.splitlines()[3:] if '\t' in line}
    names.discard('')
    if not names:
        raise ValueError('Private comparison input has no catalog rows')
    return re.compile(r'(?<![\w.])(?:' + '|'.join(map(re.escape, sorted(names, key=len, reverse=True))) + r')(?![\w.])', re.I)


def check(name, data, names):
    path = Path(name)
    reasons = []
    forbidden = path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.key', '.pem', '.pfx', '.p12', '.rpm', '.exe', '.zip', '.gz', '.bak'}
    forbidden |= bool(re.search(r'\.(?:db|sqlite3?)-(?:wal|shm)$', path.name))
    private_filename = (path.name.startswith('.env') and path.name != '.env.example') or bool(re.search(r'\.env(?:\.|$)', path.name))
    if path.name == '.env.example':
        private_filename = False
    private_filename |= path.name.lower().startswith('export all') or path.name == 'pump-status-tags.txt'
    if forbidden or private_filename:
        reasons.append('private/runtime/artifact filename')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        reviewed = (path.parent.as_posix() == 'aqua-command-desktop/fonts'
                    and REVIEWED_FONTS.get(path.name) == hashlib.sha256(data).hexdigest())
        if not reviewed:
            reasons.append('binary requires separate distribution review')
        return reasons
    for label, pattern in [('credential shape', CREDENTIAL), ('personal home path', HOME), ('private key', KEY), ('known private Tag', names)]:
        if pattern and pattern.search(text):
            reasons.append(label)
    if path.name == 'opcua_tag_mapping.json' and '/tests/' not in '/' + name:
        try:
            if json.loads(text).get('mappings'):
                reasons.append('runtime mappings must stay in private configuration')
        except (ValueError, AttributeError):
            reasons.append('invalid mapping template')
    return reasons


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Read staged blobs, never the working-tree substitutes')
    parser.add_argument('--directory', type=Path, help='Scan an extracted source or payload directory without Git')
    parser.add_argument('--private-catalog', type=Path,
                        default=os.environ.get('AQUACMD_PRIVATE_CATALOG'),
                        help='Owner-only comparison input, never copied or printed; or AQUACMD_PRIVATE_CATALOG')
    options = parser.parse_args(argv)
    if options.staged and options.directory:
        parser.error('--staged and --directory are mutually exclusive')
    names = private_names(options.private_catalog)
    directory = options.directory.resolve() if options.directory else ROOT
    if options.directory:
        files = b'\0'.join(str(p.relative_to(directory)).encode() for p in sorted(directory.rglob('*')) if p.is_file() or p.is_symlink())
    else:
        files = git('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z') if options.staged else git('ls-files', '-z')
    staged_symlinks = set()
    if options.staged:
        for entry in git('ls-files', '--stage', '-z').split(b'\0'):
            if entry:
                metadata, name = entry.split(b'\t', 1)
                if metadata.startswith(b'120000 '):
                    staged_symlinks.add(name.decode())
    failures = []
    count = 0
    for raw in files.split(b'\0'):
        if not raw:
            continue
        name = raw.decode()
        path = directory / name
        if not options.staged and not path.exists():
            continue
        count += 1
        symlink = name in staged_symlinks if options.staged else path.is_symlink()
        if symlink:
            reasons = ['symlink requires separate review']
        else:
            data = git('show', ':' + name) if options.staged else path.read_bytes()
            reasons = check(name, data, names)
        if reasons:
            failures.append({'path': name, 'reasons': reasons})
    print(json.dumps({'scope': 'index' if options.staged else ('extracted directory' if options.directory else 'current tracked tree'), 'files': count,
                      'private_catalog_comparison': bool(names), 'findings': failures,
                      'history_clearance': 'NOT_EVALUATED'}, indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
