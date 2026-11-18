"""The rules of the architecture, as tests. Each was a defect once; none can come back unnoticed.

  1. No function longer than 50 lines. A long function is where the errors of a model hide: the
     builder had one of 320 lines until 18 November 2026.
  2. No module of the package longer than 600 lines.
  3. No module of the package imports another in a circle, not even inside a function.
  4. An import inside a function is allowed only for what is optional (openLCA, the page, the GPU).
  5. The core of the agent depends on nothing but itself: no openLCA, no page, no report, no file.
  6. An error that is caught without knowing its kind is named and said, never swallowed.
"""
import ast
import glob
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = sorted(glob.glob(os.path.join(ROOT, "branch", "*.py")))
EVERYTHING = PACKAGE + sorted(
    glob.glob(os.path.join(ROOT, "experiments", "**", "*.py"), recursive=True)
    + glob.glob(os.path.join(ROOT, "examples", "*.py")) + glob.glob(os.path.join(ROOT, "packaging", "*.py"))
    + glob.glob(os.path.join(ROOT, "tests", "*.py")) + [os.path.join(ROOT, "app.py")])

MAX_FUNCTION, MAX_MODULE = 50, 600
# the model of PET against glass as it was written by hand before the builder existed, kept unchanged
# because one test compares the builder with it
KEPT_AS_WRITTEN = {"tests/legacy_pet_glass.py"}
CORE = {"beliefs", "lca_model", "montecarlo", "query", "agent", "backend"}
OPTIONAL = {"olca_extract", "olca_bridge", "webapp"}       # need openLCA's packages or the page
OPTIONAL_PACKAGES = {"olca_ipc", "olca_schema", "gradio", "cupy", "branch"}
NOT_IN_THE_CORE = {"olca_ipc", "olca_schema", "gradio", "reportlab", "matplotlib", "pandas"}


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def tree(path):
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def name(path):
    return os.path.basename(path)[:-3]


def imports(path):
    """[(module of the package that is imported, True when the import is at the top of the file)]."""
    mods, t = {name(p) for p in PACKAGE}, tree(path)
    top = {id(n) for n in t.body}
    out = []
    for n in ast.walk(t):
        if not isinstance(n, ast.ImportFrom) or not (n.level or (n.module or "").startswith("branch")):
            continue
        module = (n.module or "").replace("branch.", "").replace("branch", "")
        targets = [module] if module in mods else [a.name for a in n.names if a.name in mods]
        out += [(m, id(n) in top) for m in targets]
    return out


@pytest.mark.parametrize("path", EVERYTHING, ids=rel)
def test_no_function_is_longer_than_fifty_lines(path):
    if rel(path) in KEPT_AS_WRITTEN:
        return
    long = [(n.name, n.end_lineno - n.lineno + 1) for n in ast.walk(tree(path))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.end_lineno - n.lineno + 1 > MAX_FUNCTION]
    assert not long, f"{rel(path)}: split {long} into smaller functions with one job each"


@pytest.mark.parametrize("path", PACKAGE, ids=rel)
def test_no_module_of_the_package_is_longer_than_six_hundred_lines(path):
    with open(path, encoding="utf-8") as fh:
        assert sum(1 for _ in fh) <= MAX_MODULE, f"{rel(path)} has grown past {MAX_MODULE} lines: divide it by subject"


def test_no_module_imports_another_in_a_circle():
    graph = {name(p): {m for m, _ in imports(p)} for p in PACKAGE}
    state, circles = {}, []

    def visit(node, path):
        state[node] = "open"
        for nxt in sorted(graph[node] - {node}):
            if state.get(nxt) == "open":
                circles.append(path[path.index(nxt):] + [nxt])
            elif nxt not in state:
                visit(nxt, path + [nxt])
        state[node] = "done"

    for node in sorted(graph):
        if node not in state:
            visit(node, [node])
    assert not circles, f"modules that import each other in a circle: {circles}"


def test_an_import_inside_a_function_is_only_for_what_is_optional():
    for path in PACKAGE:
        inside = {m for m, at_top in imports(path) if not at_top}
        assert inside <= OPTIONAL, f"{rel(path)} imports {sorted(inside - OPTIONAL)} inside a function: move it to the top"
        t = tree(path)
        top = {id(n) for n in t.body}
        for n in ast.walk(t):
            if isinstance(n, ast.Import) and id(n) not in top:
                names = {a.name.split(".")[0] for a in n.names}
                assert names <= OPTIONAL_PACKAGES, f"{rel(path)} imports {sorted(names)} inside a function"


def test_the_core_of_the_agent_depends_only_on_itself():
    for path in PACKAGE:
        if name(path) in CORE:
            outside = {m for m, _ in imports(path)} - CORE
            assert not outside, f"the core module {name(path)} must not import {sorted(outside)}"
            for n in ast.walk(tree(path)):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    names = {a.name.split(".")[0] for a in n.names} | {(getattr(n, "module", None) or "").split(".")[0]}
                    assert not names & NOT_IN_THE_CORE, f"{rel(path)} imports {sorted(names & NOT_IN_THE_CORE)}"


def test_a_caught_error_of_unknown_kind_is_named_and_used():
    """`except Exception:` hides what happened. Every such handler binds the error and passes it on:
    in a message to the person, in the log, or raised again."""
    for path in PACKAGE:
        for n in ast.walk(tree(path)):
            if not isinstance(n, ast.ExceptHandler) or n.type is None:
                assert not isinstance(n, ast.ExceptHandler), f"{rel(path)} line {n.lineno}: a bare except"
                continue
            broad = isinstance(n.type, ast.Name) and n.type.id in ("Exception", "BaseException")
            if not broad:
                continue
            raises = any(isinstance(x, ast.Raise) for x in ast.walk(n))
            uses = n.name and any(isinstance(x, ast.Name) and x.id == n.name for x in ast.walk(n))
            assert raises or uses, f"{rel(path)} line {n.lineno}: the error is caught and not said"
