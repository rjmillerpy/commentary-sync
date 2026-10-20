"""Checks for the CODE_QUALITY_RULES.md rules a parser can measure.

Rules 1 and 56 (function, method and class length), 6, 24 and 42 (nesting),
32 and 33 (broad excepts), 47 (annotations), 49 (parametrize ids), 50
(schema.py) and 57 (inheritance depth). Each check reads the source with
`ast`, so it covers every file without importing any of it.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = PROJECT_ROOT / "app"

MAX_FUNCTION_LINES = 50
MAX_METHOD_LINES = 30
MAX_CLASS_LINES = 200
MAX_BLOCK_DEPTH = 3
MAX_LOOP_DEPTH = 2
MAX_APP_INHERITANCE = 1

BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)
LOOPS = (ast.For, ast.AsyncFor, ast.While)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
BROAD_EXCEPTIONS = {"Exception", "BaseException"}

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

# Workspace packages under packages/ are app code too, and every tests* folder is tests.
APP_FILES = sorted(APP_ROOT.rglob("*.py")) + sorted((PROJECT_ROOT / "packages").rglob("*.py"))
TEST_FILES = sorted(PROJECT_ROOT.glob("tests*/**/*.py"))
CODE_FILES = APP_FILES + TEST_FILES


def _relative_name(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _span(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None) or 0
    return end - getattr(node, "lineno", 0) + 1


def _functions(tree: ast.Module) -> Iterator[FunctionNode]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def _depth(node: ast.AST, counted: tuple[type[ast.AST], ...], depth: int = 0) -> int:
    """The deepest stack of `counted` nodes inside `node`, not entering nested scopes."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, SCOPES):
            continue
        child_depth = depth + 1 if isinstance(child, counted) else depth
        if isinstance(child, COMPREHENSIONS) and LOOPS[0] in counted:
            child_depth = depth + len(child.generators)
        deepest = max(deepest, _depth(child, counted, child_depth))
    return deepest


@pytest.mark.parametrize("path", CODE_FILES, ids=_relative_name)
def test_functions_and_classes_stay_short(path: Path) -> None:
    """Rules 1 and 56: functions under 50 lines, methods under 30, classes under 200."""
    tree = _parse(path)
    too_long = [
        f"{function.name} ({_span(function)} lines)"
        for function in _functions(tree)
        if _span(function) > MAX_FUNCTION_LINES
    ]
    for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        if _span(cls) > MAX_CLASS_LINES:
            too_long.append(f"class {cls.name} ({_span(cls)} lines)")
        too_long += [
            f"{cls.name}.{method.name} ({_span(method)} lines)"
            for method in cls.body
            if isinstance(method, FunctionNode) and _span(method) > MAX_METHOD_LINES
        ]
    assert not too_long


@pytest.mark.parametrize("path", CODE_FILES, ids=_relative_name)
def test_logic_nests_at_most_three_blocks_deep(path: Path) -> None:
    """Rules 6 and 42: early returns and helpers instead of deep nesting."""
    too_deep = [
        function.name
        for function in _functions(_parse(path))
        if _depth(function, BLOCKS) > MAX_BLOCK_DEPTH
    ]
    assert not too_deep


@pytest.mark.parametrize("path", CODE_FILES, ids=_relative_name)
def test_loops_nest_at_most_two_deep(path: Path) -> None:
    """Rule 24, counting comprehension clauses as loops."""
    too_deep = [
        function.name
        for function in _functions(_parse(path))
        if _depth(function, LOOPS) > MAX_LOOP_DEPTH
    ]
    assert not too_deep


@pytest.mark.parametrize("path", APP_FILES, ids=_relative_name)
def test_no_bare_or_broad_excepts(path: Path) -> None:
    """Rules 32 and 33. The app's last error boundary is a registered handler,
    not an except block, so no file needs one."""
    broad = [
        handler.lineno
        for handler in ast.walk(_parse(path))
        if isinstance(handler, ast.ExceptHandler)
        and (
            handler.type is None
            or (isinstance(handler.type, ast.Name) and handler.type.id in BROAD_EXCEPTIONS)
        )
    ]
    assert not broad, f"broad except on lines {broad}"


@pytest.mark.parametrize("path", CODE_FILES, ids=_relative_name)
def test_every_function_is_fully_annotated(path: Path) -> None:
    """Rule 47. mypy strict checks this too; this names the function."""

    def is_annotated(function: FunctionNode) -> bool:
        arguments = function.args.posonlyargs + function.args.args + function.args.kwonlyargs
        typed = [arg.annotation is not None for arg in arguments if arg.arg not in {"self", "cls"}]
        return all(typed) and function.returns is not None

    assert not [f.name for f in _functions(_parse(path)) if not is_annotated(f)]


@pytest.mark.parametrize("path", TEST_FILES, ids=_relative_name)
def test_parametrize_names_its_cases(path: Path) -> None:
    """Rule 49 and TEST-STRUCTURE: every parametrize has descriptive ids."""
    unnamed = [
        call.lineno
        for call in ast.walk(_parse(path))
        if isinstance(call, ast.Call)
        and ast.unparse(call.func).endswith("parametrize")
        and not any(keyword.arg == "ids" for keyword in call.keywords)
    ]
    assert not unnamed, f"parametrize without ids on lines {unnamed}"


def test_schema_files_are_singular() -> None:
    """Rule 50."""
    assert not list(APP_ROOT.rglob("schemas.py"))


def _base_names(cls: ast.ClassDef) -> list[str]:
    return [ast.unparse(base).split(".")[-1] for base in cls.bases]


def _app_classes() -> dict[str, list[str]]:
    """Every class in app/, with the names of its bases."""
    nodes = (node for path in APP_FILES for node in ast.walk(_parse(path)))
    return {node.name: _base_names(node) for node in nodes if isinstance(node, ast.ClassDef)}


def test_inheritance_stays_one_level_deep_in_app_code() -> None:
    """Rule 57: a class may extend an app class (a domain's base error,
    FrozenModel, Base), but not one that itself extends one."""
    classes = _app_classes()

    def app_depth(name: str, seen: frozenset[str] = frozenset()) -> int:
        app_bases = [base for base in classes.get(name, []) if base in classes and base not in seen]
        return max((1 + app_depth(base, seen | {name}) for base in app_bases), default=0)

    too_deep = [name for name in classes if app_depth(name) > MAX_APP_INHERITANCE]
    assert not too_deep


@pytest.mark.parametrize("path", APP_FILES, ids=_relative_name)
def test_runnable_modules_name_their_logger(path: Path) -> None:
    """Regression: under `python -m`, getLogger(__name__) is "__main__", outside
    `app`, so the scheduler's info lines were dropped. A module that can run as
    a script names its logger."""
    source = path.read_text()
    is_runnable = 'if __name__ == "__main__"' in source
    assert not (is_runnable and "getLogger(__name__)" in source)
