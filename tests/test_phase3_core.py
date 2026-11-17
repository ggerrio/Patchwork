"""Unit tests for Phase 3: AST code chunker and security guardrails."""

import pytest

from packages.core.ast_chunker import chunk_python_source
from packages.core.guardrails import (
    GuardrailViolationError,
    check_patch,
    is_forbidden_path,
    validate_modified_files,
    validate_patch,
    validate_unified_diff,
)

SAMPLE_PYTHON = '''"""Sample module."""

import os

CONSTANT = 42


def add(a: int, b: int) -> int:
    def inner(x: int) -> int:
        return x

    return inner(a) + b


@pytest.mark.asyncio
async def fetch_data(url: str) -> str:
    return url


class BillingService:
    def charge(self, amount: int) -> int:
        return amount
'''


def test_ast_chunker_extracts_top_level_functions_and_classes() -> None:
    chunks = chunk_python_source(SAMPLE_PYTHON, file_path="src/sample.py")
    assert len(chunks) == 3

    assert chunks[0].symbol_name == "add"
    assert chunks[0].chunk_type == "function"
    assert chunks[0].start_line == 8
    assert chunks[0].end_line == 12
    assert "def add" in chunks[0].content

    assert chunks[1].symbol_name == "fetch_data"
    assert chunks[1].chunk_type == "function"
    assert chunks[1].start_line == 15
    assert chunks[1].end_line == 17
    assert "@pytest.mark.asyncio" in chunks[1].content

    assert chunks[2].symbol_name == "BillingService"
    assert chunks[2].chunk_type == "class"
    assert chunks[2].start_line == 20
    assert chunks[2].end_line == 22


def test_ast_chunker_empty_source() -> None:
    assert chunk_python_source("   \n\n") == []


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "apps/api/.env.production",
        ".github/workflows/ci.yml",
        "migrations/001_init.sql",
        "apps/api/alembic/versions/001.py",
        "certs/server.pem",
        "keys/private.key",
        "config/secrets.json",
        "../outside.py",
        "/etc/passwd",
    ],
)
def test_forbidden_paths_blocked(path: str) -> None:
    forbidden, reason = is_forbidden_path(path)
    assert forbidden is True
    assert reason is not None


def test_blast_radius_limit_enforced() -> None:
    ok = validate_modified_files(["apps/a.py", "apps/b.py", "tests/test_a.py"])
    assert len(ok) == 3

    with pytest.raises(GuardrailViolationError, match="Blast radius exceeded"):
        validate_modified_files(["a.py", "b.py", "c.py", "d.py"])


def test_unified_diff_validation() -> None:
    valid_diff = (
        "--- a/src/calc.py\n"
        "+++ b/src/calc.py\n"
        "@@ -10,3 +10,3 @@\n"
        " def divide(a: int, b: int) -> float:\n"
        "-    return a / b\n"
        "+    return a / b if b != 0 else 0.0\n"
    )
    files = validate_unified_diff(valid_diff)
    assert files == ["src/calc.py"]

    result = validate_patch(["src/calc.py"], valid_diff)
    assert result.passed is True
    assert result.modified_files == ["src/calc.py"]

    # Invalid hunk header
    with pytest.raises(GuardrailViolationError):
        validate_unified_diff("--- a/x.py\n+++ b/x.py\n@@ invalid @@\n-a\n+b\n")

    # Diff touching a forbidden file is caught even if modified_files omits it
    forbidden_diff = (
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -1,1 +1,1 @@\n"
        "-KEY=1\n"
        "+KEY=2\n"
    )
    failed = check_patch(["src/calc.py"], forbidden_diff)
    assert failed.passed is False
    assert ".env" in failed.violated_files

