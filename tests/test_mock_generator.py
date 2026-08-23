import json
from datetime import datetime, timezone

from ingestion.validate_schema import validate_event
from scripts.generate_mock_telemetry import generate_dataset

_ANCHOR = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


def _feature_tuple(event) -> tuple:
    return (
        event["event_type"],
        event["actor_type"],
        event["metadata"]["policy_scope"],
        event["metadata"]["resource_count"],
        event["timestamp"][11:13],  # hour
    )


def test_generated_events_pass_schema_validation(tmp_path):
    out = tmp_path / "telemetry.json"
    generate_dataset(n_events=500, output_path=str(out), seed=1)

    events = json.loads(out.read_text(encoding="utf-8"))
    assert len(events) == 500
    for event in events:
        validate_event(event)  # must not raise


def test_same_seed_reproducible(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    generate_dataset(n_events=100, output_path=str(a), seed=42, now=_ANCHOR)
    generate_dataset(n_events=100, output_path=str(b), seed=42, now=_ANCHOR)
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


def test_labels_are_not_a_function_of_features(tmp_path):
    """
    Regression test for the circular-labeling flaw: the supervised target
    (risk_level) must NOT be derivable from the exported feature fields.
    If any frequently-repeated observable feature tuple carries both high
    and low labels, no deterministic classifier can be perfect -- i.e. the
    dataset contains genuine irreducible uncertainty.
    """
    out = tmp_path / "telemetry.json"
    generate_dataset(n_events=6000, output_path=str(out), seed=7)

    events = json.loads(out.read_text(encoding="utf-8"))
    by_features: dict[tuple, set[str]] = {}
    for event in events:
        by_features.setdefault(_feature_tuple(event), set()).add(event["risk_level"])

    repeated = {k: v for k, v in by_features.items() if sum(
        1 for e in events if _feature_tuple(e) == k) >= 5}
    mixed = [k for k, labels in repeated.items() if {"high", "low"} <= labels]
    assert mixed, (
        "Label leakage regression: every repeated feature tuple maps to a "
        "single risk label -- the supervised task is circular again."
    )


def test_label_distribution_in_expected_band(tmp_path):
    out = tmp_path / "telemetry.json"
    generate_dataset(n_events=6000, output_path=str(out), seed=3)

    events = json.loads(out.read_text(encoding="utf-8"))
    high_rate = sum(e["risk_level"] == "high" for e in events) / len(events)
    # Enough positives to train on; not so many the demo looks alarmist.
    assert 0.03 <= high_rate <= 0.25, f"high-rate {high_rate:.2%} outside band"
