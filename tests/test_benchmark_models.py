from backend.benchmark.benchmark_models import NumericSummary


def test_numeric_summary():
    summary = NumericSummary.from_values([1.0, 2.0, 3.0])
    assert summary.count == 3
    assert summary.median == 2.0
    assert summary.mean == 2.0


def test_empty_numeric_summary_is_explicitly_unavailable():
    summary = NumericSummary.from_values([])
    assert summary.count == 0
    assert summary.median is None
