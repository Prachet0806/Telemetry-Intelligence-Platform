import json
import random
import uuid
from datetime import datetime, timedelta

EVENT_TYPES = ["auth", "iam_change", "api_call"]
ACTOR_TYPES = ["human", "service"]
REGIONS = ["us-east-1", "us-west-2", "eu-west-1"]
RESOURCE_TYPES = ["iam_role", "s3_bucket", "ec2_instance"]

ACTIONS = {
    "auth": ["Login", "Logout"],
    "iam_change": ["AttachPolicy", "DetachPolicy", "CreateRole"],
    "api_call": ["StartInstance", "StopInstance", "ListBuckets"]
}

def random_timestamp():
    now = datetime.utcnow()
    delta_minutes = random.randint(0, 60 * 24 * 30)  # last 30 days
    return (now - timedelta(minutes=delta_minutes)).isoformat() + "Z"

def choose_actor():
    return random.choices(
        ACTOR_TYPES,
        weights=[0.75, 0.25],  # humans more common
        k=1
    )[0]

def assign_risk(event_type, actor_type, policy_scope, resource_count, hour):
    score = 0

    if actor_type == "service":
        score += 1
    if event_type == "iam_change":
        score += 2
    if policy_scope == "admin":
        score += 2
    if resource_count > 20:
        score += 2
    if hour < 6 or hour > 22:
        score += 1

    if score >= 6:
        return "high"
    elif score >= 3:
        return "medium"
    return "low"

def generate_event():
    event_type = random.choice(EVENT_TYPES)
    actor_type = choose_actor()
    action = random.choice(ACTIONS[event_type])
    policy_scope = random.choices(
        ["read", "write", "admin"],
        weights=[0.6, 0.3, 0.1],
        k=1
    )[0]

    resource_count = max(1, int(random.gauss(5, 6)))
    hour = random.randint(0, 23)

    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": random_timestamp(),
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": f"{actor_type}_{random.randint(1, 500)}",
        "source_ip": f"192.168.{random.randint(0,255)}.{random.randint(0,255)}",
        "region": random.choice(REGIONS),
        "resource_type": random.choice(RESOURCE_TYPES),
        "action": action,
        "risk_level": assign_risk(
            event_type, actor_type, policy_scope, resource_count, hour
        ),
        "metadata": {
            "policy_scope": policy_scope,
            "resource_count": resource_count,
            "login_success": random.random() > 0.05
        }
    }

def generate_dataset(n_events=10000, output_path="data/raw/telemetry_logs.json"):
    events = [generate_event() for _ in range(n_events)]
    with open(output_path, "w") as f:
        json.dump(events, f, indent=2)

    print(f"Generated {n_events} telemetry events")

if __name__ == "__main__":
    generate_dataset()
