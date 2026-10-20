import pytest
from unittest.mock import patch, MagicMock

from reporting.notifications import should_alert, send_severity_alert


_CFG = {
    "enabled": True,
    "webhook_url": "https://example.invalid/hook",
    "retry_attempts": 2,
    "retry_backoff_seconds": 0.01,  # fast for tests
    "payload_format": "slack",
}


def test_critical_exceeds_default_high_threshold():
    assert should_alert("Critical", _CFG)


def test_high_meets_high_threshold():
    assert should_alert("High", _CFG)


@pytest.mark.parametrize("severity", ["Moderate", "Low", "Unknown"])
def test_below_threshold_no_alert(severity):
    assert not should_alert(severity, _CFG)


def test_disabled_master_switch():
    cfg = {**_CFG, "enabled": False}
    assert not should_alert("Critical", cfg)


def test_missing_webhook_disables_alerting():
    cfg = {"enabled": True, "webhook_url": ""}
    assert not should_alert("Critical", cfg)


def test_env_url_overrides_yaml(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://env-override.invalid")
    cfg = {"enabled": True, "webhook_url": "https://yaml.invalid"}
    assert should_alert("Critical", cfg)  # env URL wins when set


def test_empty_env_url_does_not_override_yaml(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "")
    cfg = {"enabled": True, "webhook_url": "https://yaml.invalid"}
    assert should_alert("Critical", cfg)  # empty env string does NOT override


def test_min_severity_override():
    cfg = {**_CFG, "min_severity": "Moderate"}
    assert should_alert("Moderate", cfg)


@patch("reporting.notifications.urllib.request.build_opener")
def test_send_alert_success_on_first_try(mock_build_opener, monkeypatch):
    monkeypatch.setattr("reporting.notifications._is_url_allowed", lambda _url: True)
    mock_response = MagicMock()
    mock_response.status = 200
    mock_opener = MagicMock()
    mock_opener.open.return_value.__enter__.return_value = mock_response
    mock_build_opener.return_value = mock_opener

    brief = {
        "Severity": "High",
        "Estimated Financial Exposure": "$100,000.00",
        "Executive Summary": "Test summary",
        "Recommended Actions": ["Action 1", "Action 2"],
        "Confidence Level": "High",
        "Signal Summary": {},
    }
    assert send_severity_alert(brief, _CFG) is True
    assert mock_opener.open.call_count == 1


@patch("reporting.notifications.urllib.request.build_opener")
def test_send_alert_retry_then_success(mock_build_opener, monkeypatch):
    monkeypatch.setattr("reporting.notifications._is_url_allowed", lambda _url: True)
    mock_response = MagicMock()
    mock_response.status = 200
    # Make the mock its own context manager so side_effect entries work
    # with `with urlopen(...) as response`.
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    mock_opener = MagicMock()
    mock_opener.open.return_value.__enter__.return_value = mock_response
    mock_build_opener.return_value = mock_opener

    # First call fails, second succeeds
    mock_opener.open.side_effect = [Exception("network error"), mock_response]

    brief = {
        "Severity": "High",
        "Estimated Financial Exposure": "$100,000.00",
        "Executive Summary": "Test summary",
        "Recommended Actions": ["Action 1"],
        "Confidence Level": "High",
        "Signal Summary": {},
    }
    assert send_severity_alert(brief, _CFG) is True
    assert mock_opener.open.call_count == 2


@patch("reporting.notifications.urllib.request.build_opener")
def test_send_alert_all_retries_fail(mock_build_opener, monkeypatch):
    monkeypatch.setattr("reporting.notifications._is_url_allowed", lambda _url: True)
    mock_opener = MagicMock()
    mock_opener.open.side_effect = Exception("persistent failure")
    mock_build_opener.return_value = mock_opener

    brief = {
        "Severity": "High",
        "Estimated Financial Exposure": "$100,000.00",
        "Executive Summary": "Test summary",
        "Recommended Actions": ["Action 1"],
        "Confidence Level": "High",
        "Signal Summary": {},
    }
    assert send_severity_alert(brief, _CFG) is False
    assert mock_opener.open.call_count == 2  # retry_attempts=2


def test_payload_format_slack():
    brief = {
        "Severity": "High",
        "Estimated Financial Exposure": "$100,000.00",
        "Estimated Financial Exposure Raw": 100000.0,
        "Executive Summary": "Test",
        "Recommended Actions": ["A", "B"],
        "Confidence Level": "High",
        "Signal Summary": {"Anomaly Rate": "5%"},
    }
    # Import the private function to test
    from reporting.notifications import _build_payload
    payload = _build_payload(brief, "slack")
    assert "text" in payload
    assert "High" in payload["text"]
    assert "$100,000.00" in payload["text"]


def test_payload_format_teams():
    brief = {
        "Severity": "Critical",
        "Estimated Financial Exposure": "$500,000.00",
        "Estimated Financial Exposure Raw": 500000.0,
        "Executive Summary": "Test",
        "Recommended Actions": ["A"],
        "Confidence Level": "High",
        "Signal Summary": {},
    }
    from reporting.notifications import _build_payload
    payload = _build_payload(brief, "teams")
    assert payload["type"] == "message"
    assert "attachments" in payload
    assert "Critical" in str(payload)


def test_payload_format_pagerduty():
    brief = {
        "Severity": "High",
        "Estimated Financial Exposure": "$100,000.00",
        "Estimated Financial Exposure Raw": 100000.0,
        "Executive Summary": "Test",
        "Recommended Actions": ["A"],
        "Confidence Level": "High",
        "Signal Summary": {},
    }
    from reporting.notifications import _build_payload
    payload = _build_payload(brief, "pagerduty")
    assert payload["event_action"] == "trigger"
    # PagerDuty v2 accepts critical/error/warning/info — High maps to error.
    assert payload["payload"]["severity"] == "error"
