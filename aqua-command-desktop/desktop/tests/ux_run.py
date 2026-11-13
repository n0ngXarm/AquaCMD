"""Run GTK UX checks in an isolated headless display and disposable profile (test-only)."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
DESKTOP = ROOT / 'aqua-command-desktop'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('before','after'), required=True)
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--theme', choices=('light', 'dark'), default='light')
    parser.add_argument('--checks', action='store_true')
    parser.add_argument('--focused', action='store_true')
    parser.add_argument('--test', action='append', default=[])
    parser.add_argument('--fit', action='store_true')
    parser.add_argument('--output', type=Path, help='Keep evidence for this run separate from earlier work')
    args = parser.parse_args()
    output = (args.output or ROOT / 'artifacts' / ('ux-' + args.stage)).resolve()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ip','link','set','lo','up'], check=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='aqua-native-ux-') as temporary:
        env = os.environ.copy()
        env.update(HOME=temporary, XDG_CONFIG_HOME=temporary+'/.config', XDG_DATA_HOME=temporary+'/.local/share',
                   XDG_CACHE_HOME=temporary+'/.cache', XDG_RUNTIME_DIR=temporary+'/runtime',
                   GDK_BACKEND='wayland', WAYLAND_DISPLAY='aqua-native-ux', GTK_A11Y='none',
                   WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS='1', APP_ENV='lab',
                   TELEGRAM_EXTERNAL_DELIVERY_AUTHORIZED='false', TELEGRAM_INBOUND_POLLING_AUTHORIZED='false',
                   AQUA_TEST_OPCUA_READINESS_LOOPBACK='1', AQUA_TELEMETRY_LOOPBACK_TEST='1', AQUA_UX_TEST_PROFILE='1',
                   PYTHONPATH=str(DESKTOP/'desktop')+':'+str(DESKTOP)+':'+str(DESKTOP/'desktop/tests'))
        Path(env['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
        log = (output/'compositor-latest-raw.txt').open('wb')
        compositor = subprocess.Popen(['mutter','--headless','--wayland','--no-x11','--virtual-monitor','1920x1080',
                                      '--wayland-display',env['WAYLAND_DISPLAY']], env=env, stdout=log, stderr=subprocess.STDOUT)
        def run(name, command, timeout=240):
            with (output/(name+'-raw.txt')).open('wb') as raw:
                raw.write(('COMMAND '+shlex.join(command)+'\n').encode()); raw.flush()
                try:
                    result = subprocess.run(command, cwd=DESKTOP, env=env, stdout=raw, stderr=subprocess.STDOUT, timeout=timeout)
                    code = result.returncode
                except subprocess.TimeoutExpired:
                    code = 124
                raw.write(f'\nEXIT_CODE={code}\n'.encode())
            records.append({'name':name,'command':command,'exit_code':code})
            (output/'ux-commands.json').write_text(json.dumps(records,indent=2))
            print(name, 'exit', code, flush=True)
        try:
            for _ in range(100):
                if (Path(env['XDG_RUNTIME_DIR'])/env['WAYLAND_DISPLAY']).exists(): break
                if compositor.poll() is not None: raise RuntimeError('Headless compositor exited')
                time.sleep(.1)
            if args.capture:
                run('native-capture', [sys.executable,'-B','desktop/tests/ux_native_capture.py','--out',str(output),'--theme',args.theme],180)
            if args.focused:
                run('ux-focused', [sys.executable,'-B','-m','unittest','test_ux_desktop_polish','-v'],90)
            for name in args.test:
                run('focused-'+name.split('.')[-1], [sys.executable,'-B','-m','unittest',name,'-v'])
            if args.checks:
                run('desktop-tests', [sys.executable,'-B','-m','unittest','discover','-s','desktop/tests','-v'])
                run('source-contracts', [sys.executable,'-B','-m','unittest','discover','-s','tests','-v'])
            if args.checks or args.fit:
                for size in ('1024x496','1360x616','1920x1009'):
                    env['F3_TEST_SIZE'] = size
                    for theme in ('light', 'dark'):
                        run('f3-handoff-'+theme+'-'+size, [sys.executable,'-B','desktop/tests/ux_theme_fit.py','--theme',theme],120)
        finally:
            compositor.terminate()
            try: compositor.wait(timeout=5)
            except subprocess.TimeoutExpired: compositor.kill(); compositor.wait()
            log.close()
    return int(any(record['exit_code'] for record in records))


if __name__ == '__main__':
    raise SystemExit(main())
