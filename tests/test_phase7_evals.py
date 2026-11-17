"""Unit tests for Phase 7: 15-case benchmark dataset and evaluation runner."""

import pytest

from evals.dataset import EVAL_CASES
from evals.run_eval import format_markdown_scorecard, run_benchmark


def test_eval_dataset_has_15_unique_cases() -> None:
    assert len(EVAL_CASES) == 15
    ids = [c.case_id for c in EVAL_CASES]
    assert len(set(ids)) == 15


@pytest.mark.asyncio
async def test_eval_benchmark_local_mode_all_15_pass() -> None:
    results = await run_benchmark(mode="local")
    assert len(results) == 15
    assert all(r.passed for r in results)

    scorecard = format_markdown_scorecard(results)
    assert "Resolution Rate %" in scorecard
    assert "100.0% (15/15)" in scorecard
    assert "Avg Latency" in scorecard
    assert "Avg Tokens" in scorecard
    assert "Retry Distribution" in scorecard

