"""Check desktop annotation imports without importing GTK or application modules."""
import ast
import builtins
from pathlib import Path
import unittest

DESKTOP = Path(__file__).resolve().parents[1]


def missing_annotation_names(source):
    tree = ast.parse(source)
    bound = set(vars(builtins))
    annotations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            bound.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            bound.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        if isinstance(node, ast.arg) and node.annotation:
            annotations.append(node.annotation)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            annotations.append(node.returns)
    used = set()
    for annotation in annotations:
        for node in ast.walk(annotation):
            if isinstance(node, ast.Name):
                used.add(node.id)
    return sorted(used - bound)


class ImportCompatTests(unittest.TestCase):
    def test_all_desktop_annotations_have_bound_names(self):
        failures = {file.name: names for file in sorted(DESKTOP.glob('*.py'))
                    if (names := missing_annotation_names(file.read_text(encoding='utf-8')))}
        self.assertEqual(failures, {})

    def test_missing_optional_import_is_detected(self):
        self.assertEqual(missing_annotation_names('def f(x: Optional[dict] = None): pass'), ['Optional'])
        self.assertEqual(missing_annotation_names('from typing import Optional\ndef f(x: Optional[dict] = None): pass'), [])

    def test_app_without_optional_import_is_rejected(self):
        source = (DESKTOP / 'app.py').read_text(encoding='utf-8')
        mutated = source.replace('from typing import Optional\n', '', 1)
        self.assertNotEqual(source, mutated)
        self.assertIn('Optional', missing_annotation_names(mutated))


if __name__ == '__main__':
    unittest.main()
