import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from decision.decision_context import DecisionContext  # noqa: E402


def make_valid_event(
    event_id: str = "evt-1",
    event_type: str = "api_call",
    actor_type: str = "human",
    policy_scope: str = "read",
    resource_count: int = 5,
    risk_level: str = "low",
    timestamp: str = "2026-08-20T12:00:00Z",
) -> dict:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": f"{actor_type}_1",
        "source_ip": "192.168.0.1",
        "region": "us-east-1",
        "resource_type": "s3_bucket",
        "action": "ListBuckets",
        "risk_level": risk_level,
        "metadata": {
            "policy_scope": policy_scope,
            "resource_count": resource_count,
            "login_success": True,
        },
    }


def make_ctx(**overrides) -> DecisionContext:
    defaults = dict(
        baseline_flag_rate=0.10,
        anomaly_rate=0.05,
        high_risk_percentage=5.0,
        total_events=10000,
        admin_scope_rate=0.05,
    )
    defaults.update(overrides)
    return DecisionContext(**defaults)


@pytest.fixture
def events_df() -> pd.DataFrame:
    rows = [
        make_valid_event(event_id=f"evt-{i}",
                         event_type=("iam_change" if i % 2 else "api_call"),
                         actor_type=("service" if i % 3 == 0 else "human"),
                         policy_scope=("admin" if i % 5 == 0 else "read"),
                         resource_count=(30 if i % 7 == 0 else 5))
        for i in range(1, 21)
    ]
    df = pd.json_normalize(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df
