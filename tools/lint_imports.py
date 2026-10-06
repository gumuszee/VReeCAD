# Minimal static check of the addon sources: syntax errors, imported names that are never used, and `import x as y` aliases that shadow nothing.
# Not a replacement for a linter; it needs only the standard library, so FreeCAD's bundled Python can run it.
# Usage:  python tools/lint_imports.py [paths...]      (default: freecad/ tests/ tools/)
# Exit code 1 when something is reported.
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def python_files(paths):
    for path in paths:
        if os.path.isfile(path):
            yield path
            continue
        for folder, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "refs", "upstream")]
            for name in files:
                if name.endswith(".py") and not name.endswith("_rc.py"):
                    yield os.path.join(folder, name)


def check(path):
    with open(path, encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source, path)
    except SyntaxError as error:
        return [f"{path}:{error.lineno}: syntax error: {error.msg}"]
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    imported[alias.asname or alias.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    exported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            exported |= {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
    lines = source.splitlines()
    problems = []
    for name, lineno in sorted(imported.items(), key=lambda item: item[1]):
        if name in used or name in exported or "noqa" in lines[lineno - 1]:
            continue
        problems.append(f"{path}:{lineno}: '{name}' imported but unused")
    return problems


def main():
    paths = sys.argv[1:] or [os.path.join(ROOT, p) for p in ("freecad", "tests", "tools")]
    problems = [p for path in python_files(paths) for p in check(path)]
    for problem in problems:
        print(os.path.relpath(problem, ROOT) if os.path.isabs(problem) else problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
