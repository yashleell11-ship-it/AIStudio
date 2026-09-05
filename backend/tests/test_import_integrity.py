"""Nothing in the backend may import a module that no longer exists.

``cli.py`` — the one console script ``pyproject.toml`` declared — did
``from services.import_cleanup import ImportCleanupService`` for six months
after that service was deleted with the rest of the folder-import subsystem in
the source-native rewrite. Two things hid it. The import sat *inside* a
function, so merely importing ``cli`` still succeeded; and no test imported
``cli`` at all, because the suite only reaches modules the app reaches and a
console script is by definition the entry point the app never calls.

So a run-time check is the wrong shape here: the failure lives on a code path
nothing executes. These read the import statements themselves.
"""

from __future__ import annotations

import ast
import importlib.util
import tomllib
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: Not source: virtualenvs, byte-code and tool caches, build metadata.
_SKIP_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "manhwamaniacs_backend.egg-info",
}


def _source_files() -> list[Path]:
    return [
        path
        for path in sorted(_BACKEND_ROOT.rglob("*.py"))
        if not _SKIP_DIRS & set(path.relative_to(_BACKEND_ROOT).parts)
    ]


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    """Every absolute module name the tree imports, at any nesting depth.

    ``ast.walk`` rather than a top-level scan because the bug this file exists
    for was a deferred import inside a function body. Relative imports are
    skipped: ``level > 0`` is resolved against the importing package, which a
    file-by-file scan does not know.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module))
    return found


def _resolves(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def test_no_module_imports_something_that_does_not_exist():
    dangling: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, module_name in _imported_modules(tree):
            if not _resolves(module_name):
                rel = path.relative_to(_BACKEND_ROOT)
                dangling.append(f"{rel}:{lineno} imports '{module_name}'")

    assert not dangling, "imports that resolve to nothing:\n  " + "\n  ".join(dangling)


def test_the_scan_actually_reads_the_tree():
    """Guards the guard: a globbing mistake would make the test above vacuous."""
    files = _source_files()
    assert len(files) > 100
    assert any(path.name == "main.py" for path in files)


def _pyproject() -> dict:
    with (_BACKEND_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_packaged_modules_and_console_scripts_still_exist():
    """The other half of the same rot: a manifest naming a deleted file.

    Nothing imports a console script, so only the manifest itself says which
    modules have to be there.
    """
    config = _pyproject()
    missing: list[str] = []

    for module_name in config.get("tool", {}).get("setuptools", {}).get("py-modules", []):
        if not _resolves(module_name):
            missing.append(f"py-modules declares '{module_name}'")

    for script_name, target in config.get("project", {}).get("scripts", {}).items():
        module_name, _, attribute = target.partition(":")
        if not _resolves(module_name):
            missing.append(f"console script '{script_name}' points at missing '{target}'")
            continue
        module = importlib.import_module(module_name)
        if not callable(getattr(module, attribute, None)):
            missing.append(f"console script '{script_name}' target '{target}' is not callable")

    assert not missing, "pyproject.toml packages what is not there:\n  " + "\n  ".join(missing)
