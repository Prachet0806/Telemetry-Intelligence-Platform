import json

from ingestion.load_logs import load_telemetry
from tests.conftest import make_valid_event


def _write(path, events):
    path.write_text(json.dumps(events), encoding="utf-8")
    return str(path)


def test_dedup_keeps_first_and_reports(tmp_path):
    first = make_valid_event(event_id="dup-1", risk_level="low")
    second = make_valid_event(event_id="dup-1", risk_level="high")  # must lose
    other = make_valid_event(event_id="solo-1")
    bad = {"event_id": "bad-1"}  # missing everything else

    raw = _write(tmp_path / "raw.json", [first, second, other, bad])
    rejected = tmp_path / "rejected.json"

    df, stats = load_telemetry(raw, rejected_path=str(rejected))

    assert stats["total_events"] == 4
    assert stats["valid_events"] == 2
    assert stats["duplicate_events"] == 1
    assert stats["invalid_events"] == 1
    assert stats["error_types"]

    assert len(df) == 2
    # first occurrence wins
    row = df[df["event_id"] == "dup-1"].iloc[0]
    assert row["risk_level"] == "low"
    # timestamps parsed to datetime
    assert df["timestamp"].dtype.name.startswith("datetime64")

    import json as j
    rejected_events = j.loads(rejected.read_text(encoding="utf-8"))
    assert len(rejected_events) == 1


def test_empty_dataset_returns_empty_df(tmp_path):
    raw = _write(tmp_path / "raw.json", [])
    df, stats = load_telemetry(raw)
    assert df.empty
    assert stats["valid_events"] == 0
