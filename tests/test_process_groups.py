"""Every `os.killpg` in the pack survives EPERM (sd:7900).

macOS answers EPERM, not only ESRCH, for a group whose members are exiting
(sd:7704, sd:2402), and the gate's sandbox can deny the call outright. An
uncaught PermissionError leaves the child running and fails the caller.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: The trees the gate runs; their own tests may call killpg bare on purpose.
TREES = ("bin", "dashboard", "lib")
CAUGHT = {"PermissionError", "OSError"}


def _names(node: ast.AST | None) -> set[str]:
    return {n.id if isinstance(n, ast.Name) else n.attr for n in ast.walk(node)
            if isinstance(n, (ast.Name, ast.Attribute))} if node is not None else set()


def _guarded(call: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    child, node = call, parents.get(call)
    while node is not None:
        if isinstance(node, ast.Try) and child in node.body and any(
                CAUGHT & _names(handler.type) for handler in node.handlers):
            return True
        if isinstance(node, ast.With) and any(
                isinstance(item.context_expr, ast.Call) and "suppress" in _names(item.context_expr.func)
                and CAUGHT & set().union(*map(_names, item.context_expr.args)) for item in node.items):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return False
        child, node = node, parents.get(node)
    return False


def unguarded() -> list[str]:
    """`path:line` of each `os.killpg` call outside a handler that catches PermissionError."""
    found = []
    for tree in TREES:
        for path in sorted((ROOT / tree).rglob("*.py")):
            if "tests" in path.relative_to(ROOT).parts or ".venv" in path.parts:
                continue
            module = ast.parse(path.read_text(encoding="utf-8"))
            parents = {child: node for node in ast.walk(module) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(module):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "killpg"
                        and not _guarded(node, parents)):
                    found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return found


class KillpgSurvivesEperm(unittest.TestCase):
    def test_every_killpg_catches_permission_error(self):
        self.assertEqual(unguarded(), [])

    def test_the_guard_refuses_a_bare_call_and_one_that_catches_only_esrch(self):
        bare = ast.parse("def f(p):\n    os.killpg(p.pid, 9)\n")
        esrch = ast.parse("def f(p):\n    try:\n        os.killpg(p.pid, 9)\n    except ProcessLookupError:\n"
                          "        pass\n")
        caught = ast.parse("def f(p):\n    with contextlib.suppress(ProcessLookupError, PermissionError):\n"
                           "        os.killpg(p.pid, 9)\n")
        for module, want in ((bare, False), (esrch, False), (caught, True)):
            parents = {child: node for node in ast.walk(module) for child in ast.iter_child_nodes(node)}
            call = next(node for node in ast.walk(module) if isinstance(node, ast.Call))
            with self.subTest(source=ast.unparse(module)):
                self.assertIs(_guarded(call, parents), want)


if __name__ == "__main__":
    unittest.main()
