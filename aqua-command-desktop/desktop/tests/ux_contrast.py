"""WCAG contrast calculations from presentation CSS; no runtime or network access."""
import json
from pathlib import Path
import re
import sys

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))
from theme_tokens import DARK


def contrast(foreground, background):
    def luminance(value):
        channels = [int(value[i:i+2],16)/255 for i in (1,3,5)]
        channels = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return sum(a*b for a,b in zip(channels,(.2126,.7152,.0722)))
    a,b = sorted((luminance(foreground),luminance(background)))
    return (b+.05)/(a+.05)


def declaration(text, selector, key):
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
    return DARK[result[1:].replace('_', '-')] if result.startswith('@') else result


def measurements():
    workspace = (DESKTOP/'workspace_style.css').read_text()
    f2 = (DESKTOP/'f2_style.css').read_text()
    f1 = (DESKTOP/'f1_style.css').read_text()
    theme = (DESKTOP/'f1_api/formal-theme.css').read_text()
    dark = re.search(r':root\[data-theme="dark"\]\{([^}]+)',theme)[1]
    tokens = dict(re.findall(r'--([\w-]+):(#[0-9a-fA-F]{6})',dark))
    pairs = []
    for name, css, selector, background in [
        ('GTK disabled Task action',workspace,'.f2-btn-new-task:disabled',None),
        ('GTK standby label',f1,'.badge-standby',None),
        ('GTK running status',f2,'.f2-pill-running',None),
        ('GTK catalog badge',f2,'.f2-badge-blue',None),
    ]:
        fg = declaration(css,selector,'color')
        try: bg = declaration(css,selector,'background-color')
        except AssertionError: bg = declaration(css,selector,'background')
        pairs.append((name,fg,bg))
    for ink in ('ink','mut','faint','unv','ok','fail','stale','nb'):
        background = {'unv':'unv-tint','ok':'ok-tint','fail':'fail-tint','stale':'stale-tint','nb':'nb-tint'}.get(ink,'surface-2' if ink=='faint' else 'surface')
        pairs.append(('WebKit '+ink,tokens[ink],tokens[background]))
    return [{'sample':name,'foreground':fg,'background':bg,'contrast':round(contrast(fg,bg),3),'passes_4_5':contrast(fg,bg)>=4.5}
            for name,fg,bg in pairs]


if __name__ == '__main__':
    report = measurements()
    print(json.dumps(report,indent=2))
    raise SystemExit(int(any(not row['passes_4_5'] for row in report)))
