"""Isolated local Docker sandbox runner for executing pytest on proposed patches."""

import asyncio
import io
import logging
import tarfile
import time
from dataclasses import dataclass

import docker
from docker.errors import ContainerError, DockerException

logger = logging.getLogger(__name__)

DEFAULT_SANDBOX_IMAGE = "patchwork-sandbox:latest"


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of running tests inside an isolated Docker container."""

    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


def _build_tar_archive(files: dict[str, str]) -> bytes:
    """Bundle repository files into an in-memory TAR archive for `put_archive`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for rel_path, content in files.items():
            clean_path = rel_path.lstrip("/")
            encoded = content.encode("utf-8")
            info = tarfile.TarInfo(name=clean_path)
            info.size = len(encoded)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(encoded))
    buf.seek(0)
    return buf.getvalue()


class DockerSandboxRunner:
    """Runs `pytest` inside an isolated ephemeral Docker container."""

    def __init__(self, image: str = DEFAULT_SANDBOX_IMAGE) -> None:
        self._image = image

    def _run_sync(
        self,
        files: dict[str, str],
        test_command: str,
        timeout_seconds: int,
    ) -> SandboxResult:
        started = time.perf_counter()
        client = docker.from_env()
        container = None
        try:
            container = client.containers.create(
                image=self._image,
                command=["sh", "-c", test_command],
                working_dir="/repo",
                network_mode="none",
                mem_limit="256m",
                pids_limit=64,
                detach=True,
            )
            archive_bytes = _build_tar_archive(files)
            container.put_archive("/repo", archive_bytes)
            container.start()

            wait_result = container.wait(timeout=timeout_seconds)
            exit_code = int(wait_result.get("StatusCode", 1))
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return SandboxResult(
                passed=(exit_code == 0),
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=elapsed_ms,
            )
        except (ContainerError, DockerException, Exception) as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("Docker sandbox execution failed: %s", exc)
            return SandboxResult(
                passed=False,
                exit_code=1,
                stdout="",
                stderr=f"Docker sandbox execution error: {exc}",
                duration_ms=elapsed_ms,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception as remove_exc:
                    logger.warning("Failed to remove sandbox container: %s", remove_exc)
            client.close()

    async def run_pytest(
        self,
        files: dict[str, str],
        test_command: str = "pytest -q",
        timeout_seconds: int = 30,
    ) -> SandboxResult:
        """Write repository files into an isolated Docker container and execute `pytest`."""
        return await asyncio.to_thread(self._run_sync, files, test_command, timeout_seconds)
