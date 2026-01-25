from typing import Dict, Any

REQUIRED_FIELDS = {
    "event_id": str,
    "timestamp": str,
    "event_type": str,
    "actor_type": str,
    "actor_id": str,
    "source_ip": str,
    "region": str,
    "resource_type": str,
    "action": str,
    "risk_level": str,
    "metadata": dict,
}

METADATA_FIELDS = {
    "policy_scope": str,
    "resource_count": int,
    "login_success": bool,
}

def validate_event(event: Dict[str, Any]) -> None:
    for field, field_type in REQUIRED_FIELDS.items():
        if field not in event:
            raise ValueError(f"Missing required field: {field}")
        if not isinstance(event[field], field_type):
            raise TypeError(f"Invalid type for field '{field}'")

    metadata = event["metadata"]
    for field, field_type in METADATA_FIELDS.items():
        if field not in metadata:
            raise ValueError(f"Missing metadata field: {field}")
        if not isinstance(metadata[field], field_type):
            raise TypeError(f"Invalid type for metadata field '{field}'")
