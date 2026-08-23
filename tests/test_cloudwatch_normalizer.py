from ingestion.cloudwatch_normalizer import (
    _label_jitter,
    normalize_cloudtrail_event,
)


def _cloudtrail_record(event_id="ct-123", **overrides):
    record = {
        "eventName": "AttachRolePolicy",
        "eventSource": "iam.amazonaws.com",
        "awsRegion": "us-west-2",
        "sourceIPAddress": "10.0.0.1",
        "eventTime": "2026-08-20T14:00:00Z",
        "eventID": event_id,
        "userIdentity": {"type": "IAMUser", "userName": "alice"},
        "requestParameters": {"policyArn": "arn:aws:iam::aws:policy/AdministratorAccess"},
    }
    record.update(overrides)
    return record


def test_full_mapping():
    event = normalize_cloudtrail_event(_cloudtrail_record())

    assert event is not None
    assert event["event_id"] == "ct-123"
    assert event["event_type"] == "iam_change"
    assert event["actor_type"] == "human"
    assert event["actor_id"] == "alice"
    assert event["resource_type"] == "iam_role"
    assert event["action"] == "AttachRolePolicy"
    assert event["metadata"]["policy_scope"] == "admin"
    assert event["metadata"]["login_success"] is True


def test_error_code_sets_login_failure():
    event = normalize_cloudtrail_event(
        _cloudtrail_record(errorCode="AccessDenied")
    )
    assert event["metadata"]["login_success"] is False


def test_missing_event_name_skipped():
    assert normalize_cloudtrail_event({"eventTime": "2026-08-20T14:00:00Z"}) is None


def test_derived_event_id_stable():
    a = normalize_cloudtrail_event(_cloudtrail_record(event_id=None))
    b = normalize_cloudtrail_event(_cloudtrail_record(event_id=None))
    assert a["event_id"] == b["event_id"]


def test_risk_label_deterministic_per_event():
    rec = _cloudtrail_record()
    assert (
        normalize_cloudtrail_event(rec)["risk_level"]
        == normalize_cloudtrail_event(rec)["risk_level"]
    )


def test_risk_label_not_pure_function_of_features():
    """
    Regression for circular labeling: two events with identical observable
    fields but different ids can receive different risk labels because of
    the deterministic hash jitter.
    """
    base = dict(eventName="CreateUser", eventSource="iam.amazonaws.com",
                userIdentity={"type": "IAMUser"}, requestParameters={})
    labels = set()
    for i in range(200):
        event = normalize_cloudtrail_event(
            _cloudtrail_record(event_id=f"probe-{i}", **base)
        )
        labels.add(event["risk_level"])
    # With jitter in {-1,0,+1} around a fixed score, multiple labels occur.
    assert len(labels) >= 2, "jitter has no effect -- label is pure again"


def test_jitter_range_and_determinism():
    for suffix in range(50):
        j = _label_jitter(f"id-{suffix}")
        assert j in (-1, 0, 1)
        assert _label_jitter(f"id-{suffix}") == j
