from ingestion import cloudwatch_connector as cwc


class _FakeClient:
    def __init__(self, groups):
        self._groups = groups
        self.last_kwargs = None

    def describe_log_groups(self, **kwargs):
        self.last_kwargs = kwargs
        return {"logGroups": [{"logGroupName": g} for g in self._groups]}


class _FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self, _service):
        return self._client


def test_probe_uses_exact_pattern_not_prefix(monkeypatch):
    """
    Regression: the old probe used logGroupNamePrefix + limit=1, which
    missed the target group whenever a sibling prefix match was returned
    first. It must use an exact logGroupNamePattern.
    """
    client = _FakeClient(["CloudTrail/DefaultLogGroup"])
    monkeypatch.setattr(cwc, "_make_session", lambda region: _FakeSession(client))

    assert cwc.is_cloudwatch_available("CloudTrail/DefaultLogGroup", "us-east-1")
    assert client.last_kwargs["logGroupNamePattern"] == "CloudTrail/DefaultLogGroup"
    assert "logGroupNamePrefix" not in client.last_kwargs


def test_probe_false_when_only_sibling_group_exists(monkeypatch):
    # Sibling shares the prefix; exact group is absent.
    client = _FakeClient(["CloudTrail/SomeOtherGroup"])
    monkeypatch.setattr(cwc, "_make_session", lambda region: _FakeSession(client))

    assert not cwc.is_cloudwatch_available("CloudTrail/DefaultLogGroup", "us-east-1")


def test_probe_swallows_credential_errors(monkeypatch):
    class _ExplodingSession:
        def client(self, _):
            raise PermissionError("no creds")

    monkeypatch.setattr(cwc, "_make_session", lambda region: _ExplodingSession())
    assert not cwc.is_cloudwatch_available("any", "us-east-1")
