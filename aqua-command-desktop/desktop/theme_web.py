"""Theme injection before the first paint, retained across every WebView reload."""
import json

import gi
gi.require_version('WebKit', '6.0')
from gi.repository import WebKit

try:
    from .theme_tokens import THEMES
except ImportError:
    from theme_tokens import THEMES


def install_web_theme(web, mode, previous=None):
    if mode not in THEMES:
        raise ValueError('Unsupported presentation theme')
    source = '''(()=>{
      const apply=()=>{if(document.documentElement)document.documentElement.dataset.theme=MODE;};
      if(document.documentElement){apply();}else{
        const observer=new MutationObserver(()=>{if(document.documentElement){apply();observer.disconnect();}});
        observer.observe(document,{childList:true});
      }
    })();'''.replace('MODE', json.dumps(mode))
    manager = web.get_user_content_manager()
    if previous is not None:
        manager.remove_script(previous)
    script = WebKit.UserScript.new(source, WebKit.UserContentInjectedFrames.TOP_FRAME,
                                  WebKit.UserScriptInjectionTime.START, None, None)
    manager.add_script(script)
    if web.get_uri():
        web.evaluate_javascript(source, -1, None, None, None, None, None)
    return script
