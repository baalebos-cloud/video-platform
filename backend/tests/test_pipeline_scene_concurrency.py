"""Regression tests for parallel per-scene asset generation in pipeline_task.

generation_pipeline itself needs a live DB session (session_scope) to
exercise end-to-end, so these tests target the concurrency primitive it
relies on directly: _gather_cancel_on_error must actually run coroutines
concurrently, and must cancel the rest as soon as one fails instead of
leaving them to keep burning provider calls for a job already doomed."""
import asyncio

import pytest

from app.workers.tasks.pipeline_task import SCENE_CONCURRENCY, _gather_cancel_on_error


@pytest.mark.asyncio
async def test_gather_cancel_on_error_runs_coroutines_concurrently():
    """Three 50ms 'scene generation' coroutines should overlap in wall time,
    not run back-to-back — proving this is really fan-out, not a relabeled
    sequential loop."""
    order: list[str] = []

    async def fake_scene(name: str):
        order.append(f"{name}:start")
        await asyncio.sleep(0.05)
        order.append(f"{name}:end")
        return name

    loop = asyncio.get_event_loop()
    started = loop.time()
    results = await _gather_cancel_on_error([fake_scene("a"), fake_scene("b"), fake_scene("c")])
    elapsed = loop.time() - started

    assert results == ["a", "b", "c"]
    # All three starts happen before any end — only possible if they ran
    # concurrently rather than sequentially.
    assert order[:3] == ["a:start", "b:start", "c:start"]
    # Sequential would take ~150ms; concurrent should land well under that.
    assert elapsed < 0.12


@pytest.mark.asyncio
async def test_gather_cancel_on_error_cancels_remaining_tasks_on_first_failure():
    cancelled_flags = {"slow": False}

    async def failing_scene():
        await asyncio.sleep(0.01)
        raise ValueError("provider exploded")

    async def slow_scene():
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled_flags["slow"] = True
            raise

    with pytest.raises(ValueError, match="provider exploded"):
        await _gather_cancel_on_error([failing_scene(), slow_scene()])

    # Give the cancellation a tick to actually land before asserting.
    await asyncio.sleep(0)
    assert cancelled_flags["slow"] is True


def test_scene_concurrency_is_bounded_and_matches_the_approved_spec():
    # The approved scaling spec calls for asyncio.Semaphore(6) fan-out.
    assert SCENE_CONCURRENCY == 6
