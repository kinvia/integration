"""Unit tests for incident classification."""

from kinvia.incident import (
    StateSnapshot,
    build_baseline_payload,
    build_repair_payload,
    build_state_change_payload,
    classify_incident_type,
    is_startup_suppressed_incident,
)

MONITORED = {"light", "switch", "binary_sensor", "sensor", "update"}
EXCLUDED = {"sun.sun"}
THRESHOLD = 15


def s(state: str, **attrs):
    return StateSnapshot(state=state, attributes=attrs)


def test_state_change():
    assert classify_incident_type("light.kitchen", s("on"), s("unavailable"), monitored_domains=MONITORED, excluded_entities=EXCLUDED, battery_threshold=THRESHOLD) == "state_change"


def test_state_recovery():
    assert classify_incident_type("light.kitchen", s("unavailable"), s("on"), monitored_domains=MONITORED, excluded_entities=EXCLUDED, battery_threshold=THRESHOLD) == "state_recovery"


def test_battery_low():
    assert classify_incident_type("sensor.phone_battery", s("20", device_class="battery"), s("10", device_class="battery"), monitored_domains=MONITORED, excluded_entities=EXCLUDED, battery_threshold=THRESHOLD) == "battery_low"


def test_battery_recovered():
    assert classify_incident_type("sensor.phone_battery", s("10", device_class="battery"), s("80", device_class="battery"), monitored_domains=MONITORED, excluded_entities=EXCLUDED, battery_threshold=THRESHOLD) == "battery_recovered"


def test_system_problem():
    assert classify_incident_type("binary_sensor.leak", s("off"), s("problem"), monitored_domains=MONITORED, excluded_entities=EXCLUDED, battery_threshold=THRESHOLD) == "system_problem"


def test_update_available():
    assert classify_incident_type("update.firmware", s("off"), s("on"), monitored_domains=MONITORED, excluded_entities=EXCLUDED, battery_threshold=THRESHOLD) == "update_available"


def test_excluded_entity():
    assert classify_incident_type("sun.sun", s("above_horizon"), s("unavailable"), monitored_domains=MONITORED, excluded_entities=EXCLUDED, battery_threshold=THRESHOLD) is None


def test_build_payload_friendly_name():
    payload = build_state_change_payload("light.kitchen", s("on"), s("unavailable", friendly_name="Kitchen Light"), monitored_domains=MONITORED, excluded_entities=EXCLUDED, battery_threshold=THRESHOLD)
    assert payload is not None
    assert payload.incident_type == "state_change"
    assert payload.friendly_name == "Kitchen Light"


def test_build_repair_payload():
    payload = build_repair_payload({"issue_id": "test_issue"})
    assert payload.incident_type == "repair_event"
    assert payload.entity_id == "repairs.test_issue"


def test_build_repair_payload_remove_action():
    payload = build_repair_payload(
        {
            "action": "remove",
            "domain": "spook",
            "issue_id": "empty_floors_ground_floor",
        }
    )
    assert payload.incident_type == "repair_event"
    assert payload.entity_id == "repairs.empty_floors_ground_floor"
    assert '"action":"remove"' in payload.details


def test_startup_suppressed_incidents():
    assert is_startup_suppressed_incident("state_change") is True
    assert is_startup_suppressed_incident("state_recovery") is True
    assert is_startup_suppressed_incident("battery_low") is False
    assert is_startup_suppressed_incident("system_problem") is False


def test_baseline_unavailable():
    payload = build_baseline_payload(
        "light.kitchen",
        s("unavailable", friendly_name="Kitchen Light"),
        monitored_domains=MONITORED,
        excluded_entities=EXCLUDED,
        battery_threshold=THRESHOLD,
    )
    assert payload is not None
    assert payload.incident_type == "state_change"
    assert payload.friendly_name == "Kitchen Light"
    assert payload.old_state == ""


def test_baseline_battery_low():
    payload = build_baseline_payload(
        "sensor.phone_battery",
        s("10", device_class="battery"),
        monitored_domains=MONITORED,
        excluded_entities=EXCLUDED,
        battery_threshold=THRESHOLD,
    )
    assert payload is not None
    assert payload.incident_type == "battery_low"


def test_baseline_healthy_entity():
    payload = build_baseline_payload(
        "light.kitchen",
        s("on"),
        monitored_domains=MONITORED,
        excluded_entities=EXCLUDED,
        battery_threshold=THRESHOLD,
    )
    assert payload is None


def test_baseline_excluded_entity():
    payload = build_baseline_payload(
        "sun.sun",
        s("unavailable"),
        monitored_domains=MONITORED,
        excluded_entities=EXCLUDED,
        battery_threshold=THRESHOLD,
    )
    assert payload is None
