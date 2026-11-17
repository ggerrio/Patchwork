"""Security guardrails: blast-radius limits, forbidden-path blocking, and diff validation."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

MAX_FILES_PER_PATCH = 3

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

_FORBIDDEN_EXTENSIONS = {".pem", ".key", ".p12", ".pfx"}
_FORBIDDEN_FILENAMES = {"id_rsa", "id_ed25519", "secrets.json", "secrets.yaml", "secrets.yml"}
_FORBIDDEN_DIRS = {".github", "migrations", "alembic", "secrets"}


class GuardrailViolationError(ValueError):
    """Raised when a proposed patch violates blast-radius, path, or diff rules."""

    def __init__(self, reason: str, violated_files: list[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.violated_files = violated_files or []


@dataclass(frozen=True)
class GuardrailResult:
    """Structured outcome of a patch guardrail check."""

    passed: bool
    reason: str | None = None
    modified_files: list[str] = field(default_factory=list)
    violated_files: list[str] = field(default_factory=list)


def _normalize_repo_path(raw_path: str) -> str:
    """Normalize a repository-relative path to POSIX format."""
    cleaned = raw_path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def is_forbidden_path(raw_path: str) -> tuple[bool, str | None]:
    """Return `(True, reason)` if `raw_path` is forbidden to modify."""
    normalized = _normalize_repo_path(raw_path)
    if not normalized:
        return (True, "Empty file path is not allowed")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return (True, f"Absolute path '{raw_path}' is forbidden")

    posix_path = PurePosixPath(normalized)
    parts = [part.lower() for part in posix_path.parts]

    if ".." in parts:
        return (True, f"Path traversal '..' is forbidden in '{raw_path}'")

    filename = posix_path.name.lower()
    if filename.startswith(".env"):
        return (True, f"Environment file '{raw_path}' is forbidden")

    if posix_path.suffix.lower() in _FORBIDDEN_EXTENSIONS:
        return (True, f"Key/certificate file '{raw_path}' is forbidden")

    if filename in _FORBIDDEN_FILENAMES or "secret" in filename:
        return (True, f"Secrets file '{raw_path}' is forbidden")

    for part in parts[:-1]:
        if part in _FORBIDDEN_DIRS:
            return (True, f"Directory '{part}/' in '{raw_path}' is forbidden")

    return (False, None)


def validate_modified_files(
    modified_files: Sequence[str],
    max_files: int = MAX_FILES_PER_PATCH,
) -> list[str]:
    """Validate blast radius (`<= max_files`) and check every path against forbidden rules."""
    unique_files = list(dict.fromkeys(_normalize_repo_path(p) for p in modified_files))
    if not unique_files:
        raise GuardrailViolationError("Patch must modify at least one file")

    if len(unique_files) > max_files:
        raise GuardrailViolationError(
            f"Blast radius exceeded: patch modifies {len(unique_files)} files "
            f"(maximum allowed is {max_files}). Escalating to human.",
            violated_files=unique_files,
        )

    violated: list[str] = []
    reasons: list[str] = []
    for path in unique_files:
        forbidden, reason = is_forbidden_path(path)
        if forbidden and reason is not None:
            violated.append(path)
            reasons.append(reason)

    if violated:
        raise GuardrailViolationError(
            "; ".join(reasons),
            violated_files=violated,
        )

    return unique_files


def _strip_diff_prefix(header_path: str) -> str:
    path = header_path.split("\t", 1)[0].strip()
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def validate_unified_diff(diff_text: str) -> list[str]:
    """Validate unified diff syntax and return the list of modified file paths."""
    if not diff_text or not diff_text.strip():
        raise GuardrailViolationError("Unified diff must not be empty")

    lines = diff_text.splitlines()
    modified_files: list[str] = []
    i = 0
    found_file_diff = False

    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise GuardrailViolationError(
                    f"Malformed unified diff at line {i + 1}: '--- ' not followed by '+++ '"
                )
            old_path = _strip_diff_prefix(lines[i][4:])
            new_path = _strip_diff_prefix(lines[i + 1][4:])
            target_path = old_path if new_path == "/dev/null" else new_path
            if not target_path or target_path == "/dev/null":
                raise GuardrailViolationError("Malformed unified diff: missing target file path")

            i += 2
            hunk_count = 0
            while i < len(lines) and not lines[i].startswith(("--- ", "diff --git ")):
                hunk_line = lines[i]
                if hunk_line.startswith("@@ "):
                    if not _HUNK_HEADER_RE.match(hunk_line):
                        raise GuardrailViolationError(
                            f"Invalid unified diff hunk header at line {i + 1}: {hunk_line}"
                        )
                    hunk_count += 1
                    i += 1
                    while i < len(lines) and not lines[i].startswith(
                        ("@@ ", "--- ", "diff --git ")
                    ):
                        body_line = lines[i]
                        if not body_line.startswith((" ", "+", "-", "\\ No newline at end of file")):
                            raise GuardrailViolationError(
                                f"Invalid diff body line at line {i + 1}: {body_line!r}"
                            )
                        i += 1
                else:
                    raise GuardrailViolationError(
                        f"Unexpected line outside hunk at line {i + 1}: {hunk_line!r}"
                    )

            if hunk_count == 0:
                raise GuardrailViolationError(
                    f"File '{target_path}' has diff headers but no @@ hunks"
                )
            modified_files.append(_normalize_repo_path(target_path))
            found_file_diff = True
            continue

        if line.startswith(("diff --git ", "index ", "new file mode ", "deleted file mode ")):
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        raise GuardrailViolationError(f"Unexpected diff content at line {i + 1}: {line!r}")

    if not found_file_diff:
        raise GuardrailViolationError("Diff does not contain any valid '--- '/'+++ ' file headers")

    return list(dict.fromkeys(modified_files))


def validate_patch(
    modified_files: Sequence[str],
    diff_text: str,
    max_files: int = MAX_FILES_PER_PATCH,
) -> GuardrailResult:
    """Run all security guardrails on a proposed patch; raises `GuardrailViolationError` on fail."""
    diff_files = validate_unified_diff(diff_text)
    combined = list(dict.fromkeys([*(_normalize_repo_path(f) for f in modified_files), *diff_files]))
    validated_files = validate_modified_files(combined, max_files=max_files)
    return GuardrailResult(passed=True, modified_files=validated_files)


def check_patch(
    modified_files: Sequence[str],
    diff_text: str,
    max_files: int = MAX_FILES_PER_PATCH,
) -> GuardrailResult:
    """Non-throwing wrapper around `validate_patch` returning a `GuardrailResult`."""
    try:
        return validate_patch(modified_files, diff_text, max_files=max_files)
    except GuardrailViolationError as exc:
        return GuardrailResult(
            passed=False,
            reason=exc.reason,
            modified_files=[_normalize_repo_path(p) for p in modified_files],
            violated_files=exc.violated_files,
        )
