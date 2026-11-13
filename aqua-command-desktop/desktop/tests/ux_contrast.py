"""WCAG contrast calculations from presentation CSS; no runtime or network access."""
import json
from pathlib import Path
import re
import sys

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))
from theme_tokens import DARK, THEMES


def contrast(foreground, background):
    def luminance(value):
        channels = [int(value[i:i+2],16)/255 for i in (1,3,5)]
        channels = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return sum(a*b for a,b in zip(channels,(.2126,.7152,.0722)))
    a,b = sorted((luminance(foreground),luminance(background)))
    return (b+.05)/(a+.05)


def declaration(text, selector, key, tokens=None):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    result = None
    for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}',text):
        if selector not in [item.strip() for item in selectors.split(',')]:
            continue
        values = re.findall(r'(?<![-\w])'+re.escape(key)+r'\s*:\s*(#[0-9a-fA-F]{6}|@[\w_]+)',body)
        if values:
            result = values[-1]
    if result is None:
        raise AssertionError(f'Missing CSS {selector} {key}')
    return (tokens or DARK)[result[1:].replace('_', '-')] if result.startswith('@') else result


def measurements():
    rows = []
    for mode, tokens in THEMES.items():
        pairs = []
        for name, file, selector in [
            ('GTK disabled Task action', 'workspace_style.css', '.f2-btn-new-task:disabled'),
            ('GTK standby label', 'f1_style.css', '.badge-standby'),
            ('GTK running status', 'f2_style.css', '.f2-pill-running'),
            ('GTK catalog badge', 'f2_style.css', '.f2-badge-blue'),
        ]:
            css = (DESKTOP / file).read_text()
            fg = declaration(css, selector, 'color', tokens)
            try: bg = declaration(css, selector, 'background-color', tokens)
            except AssertionError: bg = declaration(css, selector, 'background', tokens)
            pairs.append((name, fg, bg))
        for ink in ('ink', 'mut', 'faint', 'unv', 'ok', 'fail', 'stale', 'blocked', 'nb'):
            bg = ink+'-tint' if ink+'-tint' in tokens else 'surface-2' if ink=='faint' else 'surface'
            pairs.append((ink, tokens[ink], tokens[bg]))
        for name, fg, bg in [
            ('Primary', 'on-accent', 'accent'), ('Primary hover', 'on-accent', 'accent-hover'),
            ('Secondary', 'ink', 'surface'), ('Secondary hover', 'ink', 'surface-3'),
            ('Secondary pressed', 'ink', 'selected'), ('Ghost hover', 'link', 'accent-tint'),
            ('Danger', 'danger-ink', 'danger-bg'), ('Danger hover', 'fail', 'fail-tint'),
            ('Disabled', 'mut', 'surface-2'), ('Header', 'header-ink', 'header-bg'),
            ('Header secondary', 'header-mut', 'header-bg'), ('F6 status', 'mut', 'surface'),
        ]:
            pairs.append((name, tokens[fg], tokens[bg]))
        for name, fg, bg in pairs:
            value = contrast(fg, bg)
            rows.append(dict(theme=mode, sample=name, foreground=fg, background=bg,
                             contrast=round(value,3), passes_4_5=value>=4.5))
    return rows


def ui_measurements():
    rows = []
    for mode, tokens in THEMES.items():
        for name, fg in [('Control border', 'line-strong'), ('Focus', 'accent'), ('Grid', 'grid'),
                         *[(key, key) for key in ('g1','g2','g3','g4','g5','ok','fail','stale','blocked','unv','nb')]]:
            for bg in ('bg', 'surface', 'surface-2'):
                value = contrast(tokens[fg], tokens[bg])
                rows.append(dict(theme=mode, sample=name+' on '+bg, foreground=tokens[fg], background=tokens[bg],
                                 contrast=round(value,3), passes_3=value>=3))
    return rows


if __name__ == '__main__':
    text, ui = measurements(), ui_measurements()
    print(json.dumps({'text':text,'ui':ui}, indent=2))
    raise SystemExit(int(any(not row['passes_4_5'] for row in text) or any(not row['passes_3'] for row in ui)))
