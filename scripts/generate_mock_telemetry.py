import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

EVENT_TYPES = ["auth", "iam_change", "api_call"]
ACTOR_TYPES = ["human", "service"]
REGIONS = ["us-east-1", "us-west-2", "eu-west-1"]
RESOURCE_TYPES = ["iam_role", "s3_bucket", "ec2_instance"]

ACTIONS = {
    "auth": ["Login", "Logout"],
    "iam_change": ["AttachPolicy", "DetachPolicy", "CreateRole"],
    "api_call": ["StartInstance", "StopInstance", "ListBuckets"]
}


def random_timestamp(rng: random.Random, anchor: datetime) -> str:
    delta_minutes = rng.randint(0, 60 * 24 * 30)  # last 30 days
    ts = anchor - timedelta(minutes=delta_minutes)
    return ts.isoformat().replace("+00:00", "Z")


def choose_actor(rng: random.Random) -> str:
    return rng.choices(
        ACTOR_TYPES,
        weights=[0.75, 0.25],  # humans more common
        k=1
    )[0]


def _observable_score(event_type, actor_type, policy_scope, resource_count, hour) -> int:
    """Risk evidence visible in the exported event fields."""
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

    return score


def _actor_pool(rng: random.Random, size: int = 500) -> dict[str, float]:
    """
    Latent ground truth: each actor carries a hidden compromise/risk
    propensity. This state is deliberately NOT written into any event field,
    which is what makes the downstream supervised-learning problem genuine
    rather than a lookup of a deterministic formula.
    """
    return {f"{a}_{i}": rng.random() for i in range(1, size + 1) for a in ("human", "service")}


def assign_risk(
    event_type,
    actor_type,
    policy_scope,
    resource_count,
    hour,
    latent_propensity: float,
    rng: random.Random,
) -> str:
    """
    Probabilistic labelling.

    The label is a stochastic function of the observable score PLUS the
    actor's hidden propensity. Two events with identical observable features
    can therefore receive different labels, so no classifier can reach 100%
    by construction -- evaluation metrics reflect real signal, not leakage.
    """
    score = _observable_score(event_type, actor_type, policy_scope, resource_count, hour)

    p_high = min(0.01 + 0.03 * score + 0.12 * latent_propensity, 0.90)
    p_medium = min(0.08 + 0.04 * score, max(0.90 - p_high, 0.0))

    roll = rng.random()
    if roll < p_high:
        return "high"
    if roll < p_high + p_medium:
        return "medium"
    return "low"


def generate_event(
    actor_propensity: dict[str, float],
    rng: random.Random,
    anchor: datetime,
) -> dict:
    event_type = rng.choice(EVENT_TYPES)
    actor_type = choose_actor(rng)
    action = rng.choice(ACTIONS[event_type])
    policy_scope = rng.choices(
        ["read", "write", "admin"],
        weights=[0.6, 0.3, 0.1],
        k=1
    )[0]

    resource_count = max(0, min(1000, int(rng.gauss(5, 6))))
    if resource_count < 1:
        resource_count = 1
    hour = rng.randint(0, 23)
    actor_id = f"{actor_type}_{rng.randint(1, 500)}"
    latent = actor_propensity.get(actor_id, rng.random())

    return {
        "event_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
        "timestamp": random_timestamp(rng, anchor),
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "source_ip": f"192.168.{rng.randint(0,255)}.{rng.randint(0,255)}",
        "region": rng.choice(REGIONS),
        "resource_type": rng.choice(RESOURCE_TYPES),
        "action": action,
        "risk_level": assign_risk(
            event_type, actor_type, policy_scope, resource_count, hour,
            latent_propensity=latent, rng=rng,
        ),
        "metadata": {
            "policy_scope": policy_scope,
            "resource_count": resource_count,
            "login_success": rng.random() > 0.05
        }
    }


def generate_dataset(
    n_events: int = 10000,
    output_path: str = "data/raw/telemetry_logs.json",
    seed: int | None = None,
    now: datetime | None = None,
    scenario: str = "baseline",
) -> None:
    """
    Generate synthetic CloudTrail-style telemetry.

    Parameters
    ----------
    n_events : number of events to produce.
    output_path : where to write the JSON array.
    seed : optional RNG seed for fully reproducible datasets.
    now : anchor time for event timestamps. Defaults to the current UTC
        time; pass a fixed value (together with `seed`) for byte-identical
        outputs across runs.
    scenario : baseline | attack | drift | spike — deterministic overlays (#22).
    """
    rng = random.Random(seed)
    anchor = now or datetime.now(timezone.utc)
    actor_propensity = _actor_pool(rng)

    events = [generate_event(actor_propensity, rng, anchor) for _ in range(n_events)]
    # Scenario overlays (#22): deterministic, seeded
    if scenario == "attack":
        for e in events[: max(1, n_events // 10)]:
            e["event_type"] = "iam_change"
            e["metadata"]["policy_scope"] = "admin"
            e["metadata"]["resource_count"] = 500
            e["risk_level"] = "high"
    elif scenario == "spike":
        for e in events[: max(1, n_events // 5)]:
            e["timestamp"] = anchor.isoformat().replace("+00:00", "Z")
    elif scenario == "drift":
        for e in events:
            if rng.random() < 0.3:
                e["actor_type"] = "service"
                e["region"] = "eu-west-1"

    import os
    if n_events <= 0:
        raise ValueError("n_events must be a positive integer")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)
    os.replace(tmp_path, output_path)

    print(f"Generated {n_events} telemetry events (seed={seed})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate mock telemetry.")
    parser.add_argument("--n-events", type=int, default=10000)
    parser.add_argument("--output-path", default="data/raw/telemetry_logs.json")
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed for reproducible datasets.")
    parser.add_argument("--now", type=str, default=None,
                        help="Anchor ISO timestamp (e.g. 2026-01-01T00:00:00Z) for reproducible timestamps.")
    parser.add_argument("--scenario", type=str, default="baseline",
                        choices=["baseline", "attack", "drift", "spike"])
    args = parser.parse_args()

    anchor = None
    if args.now:
        anchor = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)

    generate_dataset(
        n_events=args.n_events,
        output_path=args.output_path,
        seed=args.seed,
        now=anchor,
        scenario=args.scenario,
    )
