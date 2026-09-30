from datetime import datetime, timezone
from backend.models.execution_profile import ExecutionProfile


def test_execution_profile_preserves_unavailable_metrics():
    now = datetime.now(timezone.utc)
    profile = ExecutionProfile(
        id="p1", run_id="r1", application_path="workload.py",
        start_time=now, end_time=now, peak_working_set_bytes=None,
    )
    assert profile.cpu_cycle_count is None
    assert profile.context_switches is None
    assert profile.provenance == []
