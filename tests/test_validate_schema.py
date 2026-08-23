import pytest

from ingestion.validate_schema import validate_event
from tests.conftest import make_valid_event


def test_valid_event_passes():
    validate_event(make_valid_event())


@pytest.mark.parametrize("missing", [
    "event_id", "timestamp", "event_type", "actor_type", "metadata",
])
def test_missing_field_rejected(missing):
    event = make_valid_event()
    del event[missing]
    with pytest.raises(ValueError, match=missing):
        validate_event(event)


def test_wrong_top_level_type_rejected():
    event = make_valid_event()
    event["risk_level"] = 3
    with pytest.raises(TypeError):
        validate_event(event)


def test_wrong_metadata_type_rejected():
    event = make_valid_event()
    event["metadata"]["resource_count"] = "5"
    with pytest.raises(TypeError):
        validate_event(event)


def test_missing_metadata_field_rejected():
    event = make_valid_event()
    del event["metadata"]["policy_scope"]
    with pytest.raises(ValueError, match="policy_scope"):
        validate_event(event)


# --- New enum / timestamp / bool checks ---

@pytest.mark.parametrize("bad_type", ["hack", "phish", "sql_injection"])
def test_invalid_event_type_rejected(bad_type):
    event = make_valid_event(event_type=bad_type)
    with pytest.raises(ValueError, match="event_type"):
        validate_event(event)


@pytest.mark.parametrize("bad_actor", ["bot", "script", "ai"])
def test_invalid_actor_type_rejected(bad_actor):
    event = make_valid_event(actor_type=bad_actor)
    with pytest.raises(ValueError, match="actor_type"):
        validate_event(event)


@pytest.mark.parametrize("bad_risk", ["critical", "none", "extreme"])
def test_invalid_risk_level_rejected(bad_risk):
    event = make_valid_event(risk_level=bad_risk)
    with pytest.raises(ValueError, match="risk_level"):
        validate_event(event)


@pytest.mark.parametrize("bad_scope", ["owner", "administer", "superuser"])
def test_invalid_policy_scope_rejected(bad_scope):
    event = make_valid_event()
    event["metadata"]["policy_scope"] = bad_scope
    with pytest.raises(ValueError, match="policy_scope"):
        validate_event(event)


def test_unparseable_timestamp_rejected():
    event = make_valid_event(timestamp="not-a-timestamp")
    with pytest.raises(ValueError, match="Invalid timestamp"):
        validate_event(event)


def test_valid_iso_timestamps_accepted():
    """Both Z-suffix and +00:00 offset are accepted."""
    for ts in ("2026-08-20T12:00:00Z", "2026-08-20T12:00:00+00:00"):
        validate_event(make_valid_event(timestamp=ts))


def test_bool_rejected_for_resource_count():
    event = make_valid_event()
    event["metadata"]["resource_count"] = True  # bool is a subclass of int
    with pytest.raises(TypeError, match="resource_count"):
        validate_event(event)


def test_invalid_timestamp_format_rejected():
    """Non-ISO strings are rejected (not just unparseable, but wrong format)."""
    event = make_valid_event(timestamp="2026/08/20 12:00:00")
    with pytest.raises(ValueError, match="Invalid timestamp"):
        validate_event(event)