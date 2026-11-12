"""Pure token/parity checks; importing the application or GTK is unnecessary."""
import ast
from pathlib import Path
import re
import sys
import unittest

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))
from theme_tokens import DARK, LIGHT, gtk_definitions


def native_sources():
    tree = ast.parse((DESKTOP / 'app.py').read_text())
    inline = next(ast.literal_eval(node.value).decode() for node in tree.body
                  if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CSS_DATA' for t in node.targets))
    return [inline] + [(DESKTOP / name).read_text() for name in
                       ('style.css', 'f1_style.css', 'f2_style.css', 'workspace_style.css')]


class ThemeTokenTests(unittest.TestCase):
    def test_both_themes_have_identical_token_names(self):
        self.assertEqual(set(LIGHT), set(DARK))

    def test_static_web_tokens_match_python_exactly(self):
        css = (DESKTOP / 'f1_api/formal-theme.css').read_text()
        for selector, expected in [(':root', LIGHT), (':root[data-theme="dark"]', DARK)]:
            body = re.search(re.escape(selector) + r'\{([^}]+)\}', css)[1]
            actual = dict((key, value.strip()) for key, value in re.findall(r'--([\w-]+):([^;]+)', body))
            self.assertEqual(actual, expected)

    def test_native_styles_contain_no_literal_colours(self):
        for source in native_sources():
            self.assertNotRegex(source, r'#[0-9a-fA-F]{3,8}\b|rgba?\(')

    def test_every_native_symbolic_colour_is_defined(self):
        for theme in ('light', 'dark'):
            sources = [gtk_definitions(theme), *native_sources()]
            defined = set(re.findall(r'@define-color\s+([\w_-]+)', '\n'.join(sources)))
            used = set(re.findall(r'@([\w_-]+)', '\n'.join(sources))) - {'define-color', 'keyframes'}
            self.assertEqual(used - defined, set())


if __name__ == '__main__':
    unittest.main()
