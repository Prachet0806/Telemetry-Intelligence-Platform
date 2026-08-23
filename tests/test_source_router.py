import json

import pandas as pd

from ingestion import source_router
from tests.conftest import make_valid_event


def _cloudtrail_payload():
    return [{
        "eventName": "ConsoleLogin",
        "eventSource": "signin.amazonaws.com",
        "awsRegion": "us-east-1",
        "sourceIPAddress": "1.2.3.4",
        "eventTime": "2026-08-20T10:00:00Z",
        "eventID": "abc-1",
        "userIdentity": {"type": "IAMUser", "userName": "bob"},
    }]


def test_cloudwatch_success_caches_and_reports_source(tmp_path, monkeypatch):
    raw_path = tmp_path / "raw" / "telemetry_logs.json"
    monkeypatch.setattr(source_router, "is_cloudwatch_available", lambda lg, r: True)
    monkeypatch.setattr(source_router, "fetch_cloudwatch_events", lambda **kw: _cloudtrail_payload())

    df, stats = source_router.load_telemetry_auto(
        raw_path=str(raw_path), rejected_path=str(tmp_path / "rej.json")
    )

    assert stats["data_source"] == "cloudwatch"
    assert stats["cloudwatch_raw_events"] == 1
    assert not df.empty
    # events cached for offline fallback
    cached = json.loads(raw_path.read_text(encoding="utf-8"))
    assert len(cached) == 1


def test_fallback_to_existing_local_file(tmp_path, monkeypatch):
    raw_path = tmp_path / "telemetry_logs.json"
    raw_path.write_text(json.dumps([make_valid_event()]), encoding="utf-8")

    monkeypatch.setattr(source_router, "is_cloudwatch_available", lambda lg, r: False)

    df, stats = source_router.load_telemetry_auto(
        raw_path=str(raw_path), rejected_path=str(tmp_path / "rej.json")
    )
    assert stats["data_source"] == "local"
    assert len(df) == 1


def test_mock_generated_when_no_local_file(tmp_path, monkeypatch):
    """Fresh run with no CloudWatch and no cache must auto-generate mock data."""
    raw_path = tmp_path / "sub" / "telemetry_logs.json"

    def _fake_generate(output_path, **kw):
        path = source_router.Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([
            make_valid_event(event_id="mock-1"),
            make_valid_event(event_id="mock-2"),
        ]), encoding="utf-8")

    import scripts.generate_mock_telemetry as gen
    monkeypatch.setattr(gen, "generate_dataset", _fake_generate)
    monkeypatch.setattr(source_router, "is_cloudwatch_available", lambda lg, r: False)

    df, stats = source_router.load_telemetry_auto(
        raw_path=str(raw_path), rejected_path=str(tmp_path / "rej.json")
    )
    assert stats["data_source"] == "mock"
    assert len(df) == 2


def test_zero_cloudwatch_events_falls_back(tmp_path, monkeypatch):
    raw_path = tmp_path / "telemetry_logs.json"
    raw_path.write_text(json.dumps([make_valid_event()]), encoding="utf-8")

    monkeypatch.setattr(source_router, "is_cloudwatch_available", lambda lg, r: True)
    monkeypatch.setattr(source_router, "fetch_cloudwatch_events", lambda **kw: [])

    df, stats = source_router.load_telemetry_auto(
        raw_path=str(raw_path), rejected_path=str(tmp_path / "rej.json")
    )
    assert stats["data_source"] == "local"
