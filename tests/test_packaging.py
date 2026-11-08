"""Packaging tests: grimoire must import from any checkout, not just one named grimoire.

The code used to sit at the repository root with an __init__.py there, so
`import grimoire` only worked when the checkout folder happened to be called
grimoire and its parent was on sys.path (which pytest arranged). A clone into
any other folder failed to collect a single test, and the wheel build failed
because hatchling found no grimoire package. These tests copy the repo into a
folder with a different name and use a fresh interpreter, so pytest's own
sys.path handling for this run cannot hide the problem.
"""
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache")


def _checkout(tmp_path: Path) -> Path:
    """Copy the repo into a folder that is not called grimoire."""
    dest = tmp_path / "checkout"
    shutil.copytree(REPO, dest, ignore=SKIP)
    return dest


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True, check=False,
    )


def test_package_lives_where_the_build_backend_looks():
    # hatchling ships the folder named after the project; a package at the
    # repo root leaves it nothing to build.
    name = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["name"]
    assert (REPO / name / "__init__.py").is_file()
    assert not (REPO / "__init__.py").exists()


def test_every_module_imports_from_a_checkout_with_another_name(tmp_path):
    checkout = _checkout(tmp_path)
    modules = sorted(
        ".".join(p.relative_to(checkout).with_suffix("").parts)
        for p in (checkout / "grimoire").rglob("*.py")
        if p.name != "__init__.py"
    )
    assert modules, "no modules found under grimoire/"
    code = (
        "import importlib, grimoire\n"
        f"for m in {modules!r}: importlib.import_module(m)\n"
        "print(grimoire.__file__)\n"
    )
    result = _run(["-c", code], checkout)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).is_relative_to(checkout)


def test_suite_runs_from_a_checkout_with_another_name(tmp_path):
    checkout = _checkout(tmp_path)
    result = _run(
        ["-m", "pytest", "-q", "-p", "no:cacheprovider", "--ignore=tests/test_packaging.py"],
        checkout,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert " passed" in result.stdout
