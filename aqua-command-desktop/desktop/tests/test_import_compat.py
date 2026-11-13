"""Check desktop annotation imports without importing GTK or application modules.

Validates that all type annotations in desktop/*.py reference names that are
bound in scope prior to definition time, guarding against definition-time NameError
on Python <= 3.13 where type annotations are evaluated eagerly.

Sequential Scoping Implementation:
Statements at module and class body levels are traversed in execution order.
Import statements, variable assignments, and class/function definitions add
names to the current bound set. Function argument/return annotations and class
base classes / attribute annotations are evaluated against names bound up to
that definition point.

Limitations:
- Does not simulate dynamic runtime imports executed inside functions or methods.
- Does not parse string annotations (e.g. forward references enclosed in quotes
  like 'ClassName', which are safe under Python <= 3.13).
- Assumes branches of top-level 'if' / 'try' blocks may contribute to bound names
  (consistent with Python module initialization where fallback imports bind names).
"""
import ast
import builtins
from pathlib import Path
import unittest

DESKTOP = Path(__file__).resolve().parents[1]


def remove_optional_from_typing_import(source: str) -> str:
    """Parse source with AST and remove only the 'Optional' alias from typing imports."""
    tree = ast.parse(source)

    class OptionalRemover(ast.NodeTransformer):
        def visit_ImportFrom(self, node: ast.ImportFrom):
            if node.module == 'typing':
                node.names = [a for a in node.names if a.name != 'Optional']
                if not node.names:
                    return None
            return node

    new_tree = OptionalRemover().visit(tree)
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree)


def missing_annotation_names(source: str):
    """Detect unbound type annotations, checking sequential scoping at module and class levels."""
    tree = ast.parse(source)
    bound = set(vars(builtins))
    unbound = []

    def check_annotation(ann, current_bound):
        for n in ast.walk(ann):
            if isinstance(n, ast.Name) and n.id not in current_bound:
                if n.id not in unbound:
                    unbound.append(n.id)

    def bind_from_node(stmt, current_bound):
        if isinstance(stmt, ast.Import):
            for a in stmt.names:
                current_bound.add(a.asname or a.name.split('.')[0])
        elif isinstance(stmt, ast.ImportFrom):
            for a in stmt.names:
                current_bound.add(a.asname or a.name)
        elif isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        current_bound.add(n.id)
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name):
                current_bound.add(stmt.target.id)

    def process_body(body_nodes, current_bound):
        for stmt in body_nodes:
            if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.Assign)):
                bind_from_node(stmt, current_bound)
            elif isinstance(stmt, ast.AnnAssign):
                check_annotation(stmt.annotation, current_bound)
                bind_from_node(stmt, current_bound)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in stmt.args.posonlyargs + stmt.args.args + stmt.args.kwonlyargs:
                    if arg.annotation:
                        check_annotation(arg.annotation, current_bound)
                if stmt.args.vararg and stmt.args.vararg.annotation:
                    check_annotation(stmt.args.vararg.annotation, current_bound)
                if stmt.args.kwarg and stmt.args.kwarg.annotation:
                    check_annotation(stmt.args.kwarg.annotation, current_bound)
                if stmt.returns:
                    check_annotation(stmt.returns, current_bound)
                current_bound.add(stmt.name)
            elif isinstance(stmt, ast.ClassDef):
                for base in stmt.bases:
                    check_annotation(base, current_bound)
                class_bound = set(current_bound)
                for item in stmt.body:
                    if isinstance(item, (ast.Import, ast.ImportFrom, ast.Assign)):
                        bind_from_node(item, class_bound)
                    elif isinstance(item, ast.AnnAssign):
                        check_annotation(item.annotation, class_bound)
                        bind_from_node(item, class_bound)
                    elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for arg in item.args.posonlyargs + item.args.args + item.args.kwonlyargs:
                            if arg.annotation:
                                check_annotation(arg.annotation, class_bound)
                        if item.returns:
                            check_annotation(item.returns, class_bound)
                        class_bound.add(item.name)
                    elif isinstance(item, (ast.If, ast.Try)):
                        process_body([item], class_bound)
                current_bound.add(stmt.name)
            elif isinstance(stmt, ast.If):
                process_body(stmt.body, current_bound)
                process_body(stmt.orelse, current_bound)
            elif isinstance(stmt, ast.Try):
                process_body(stmt.body, current_bound)
                for h in stmt.handlers:
                    process_body(h.body, current_bound)
                process_body(stmt.orelse, current_bound)
                process_body(stmt.finalbody, current_bound)
            elif isinstance(stmt, (ast.For, ast.While, ast.With, ast.AsyncFor, ast.AsyncWith)):
                for child in ast.iter_child_nodes(stmt):
                    if isinstance(child, list):
                        process_body(child, current_bound)
                    else:
                        for n in ast.walk(child):
                            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                                current_bound.add(n.id)

    process_body(tree.body, bound)
    return sorted(unbound)


class ImportCompatTests(unittest.TestCase):
    def test_all_desktop_annotations_have_bound_names(self):
        failures = {file.name: names for file in sorted(DESKTOP.glob('*.py'))
                    if (names := missing_annotation_names(file.read_text(encoding='utf-8')))}
        self.assertEqual(failures, {})

    def test_missing_optional_import_is_detected(self):
        self.assertEqual(missing_annotation_names('def f(x: Optional[dict] = None): pass'), ['Optional'])
        self.assertEqual(missing_annotation_names('from typing import Optional\ndef f(x: Optional[dict] = None): pass'), [])

    def test_forward_reference_in_annotation_is_detected(self):
        code_fail = "def f(x: DeviceInfo): pass\nclass DeviceInfo: pass"
        self.assertEqual(missing_annotation_names(code_fail), ['DeviceInfo'])
        code_pass = "class DeviceInfo: pass\ndef f(x: DeviceInfo): pass"
        self.assertEqual(missing_annotation_names(code_pass), [])

    def test_app_without_optional_import_is_rejected(self):
        source = (DESKTOP / 'app.py').read_text(encoding='utf-8')
        mutated = remove_optional_from_typing_import(source)
        self.assertNotEqual(source, mutated)
        self.assertIn('Optional', missing_annotation_names(mutated))


if __name__ == '__main__':
    unittest.main()
