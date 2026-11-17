"""Redis-backed incident fingerprint deduplicator enforcing idempotency."""

import hashlib
import logging
import re

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_TRACEBACK_FRAME_RE = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+)')
DEFAULT_DEDUP_TTL_SECONDS = 3600
DEDUP_BLOCKED_COUNTER_KEY = "patchwork:metrics:duplicates_blocked"


def extract_location_from_stack_trace(stack_trace: str) -> tuple[str, int]:
    """Extract the deepest `(file_path, line_number)` frame from a Python stack trace."""
    matches = _TRACEBACK_FRAME_RE.findall(stack_trace)
    if not matches:
        return ("unknown", 0)
    file_path, line_str = matches[-1]
    return (file_path.strip(), int(line_str))


def compute_fingerprint(error_type: str, file_path: str, line_number: int) -> str:
    """Compute a deterministic SHA-256 fingerprint from error_type, file_path, and line_number."""
    raw = f"{error_type.strip()}:{file_path.strip()}:{line_number}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IncidentDeduplicator:
    """Enforces 3600-second idempotency windows on incident fingerprints via Redis."""

    def __init__(self, redis_client: Redis, ttl_seconds: int = DEFAULT_DEDUP_TTL_SECONDS) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(fingerprint: str) -> str:
        return f"patchwork:incident:dedup:{fingerprint}"

    async def acquire_lock(self, fingerprint: str, value: str = "1") -> bool:
        """Atomically claim a fingerprint lock (`SET key value NX EX 3600`).

        Returns True if newly claimed (process incident), False if duplicate.
        """
        key = self._key(fingerprint)
        acquired = await self._redis.set(key, value, nx=True, ex=self._ttl_seconds)
        if not acquired and hasattr(self._redis, "incr"):
            await self._redis.incr(DEDUP_BLOCKED_COUNTER_KEY)
        return bool(acquired)

    async def release_lock(self, fingerprint: str) -> None:
        """Release a previously acquired fingerprint lock (e.g., on DB/enqueue failure)."""
        key = self._key(fingerprint)
        await self._redis.delete(key)
