"""Incident classification ported from the Kinvia HA blueprint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .const import INVALID_STATES


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """Minimal HA state representation for classification."""

    state: str
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class HaContext:
    """Home Assistant metadata attached to incident payloads."""

    ha_version: str | None = None
    ha_location: str | None = None
    ha_timezone: str | None = None
    device: dict[str, str] | None = None
    area: dict[str, str] | None = None
    entity_registry: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class IncidentPayload:
    """Webhook payload sent to Kinvia."""

    incident_type: str
    entity_id: str
    friendly_name: str
    domain: str
    device_class: str
    state: str
    details: str
    old_state: str = ""
    new_state: dict[str, Any] | None = None
    old_state_obj: dict[str, Any] | None = None
    context: HaContext = field(default_factory=HaContext)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "incident_type": self.incident_type,
            "entity_id": self.entity_id,
            "friendly_name": self.friendly_name,
            "domain": self.domain,
            "state": self.state,
        }
        if self.device_class:
            payload["device_class"] = self.device_class
        if self.details:
            payload["details"] = self.details
        if self.old_state:
            payload["old_state"] = self.old_state
        if self.new_state is not None:
            payload["new_state"] = self.new_state
        if self.old_state_obj is not None:
            payload["old_state_obj"] = self.old_state_obj
        if self.context.device:
            payload["device"] = self.context.device
        if self.context.area:
            payload["area"] = self.context.area
        if self.context.entity_registry:
            payload["entity_registry"] = self.context.entity_registry
        if self.context.ha_version:
            payload["ha_version"] = self.context.ha_version
        if self.context.ha_location:
            payload["ha_location"] = self.context.ha_location
        if self.context.ha_timezone:
            payload["ha_timezone"] = self.context.ha_timezone
        return payload


def domain_for(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


def _float_or(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _device_class(
    new_state: StateSnapshot | None,
    registry_device_class: str | None,
) -> str | None:
    if new_state and new_state.attributes.get("device_class"):
        return str(new_state.attributes["device_class"])
    return registry_device_class


def _state_value(state: StateSnapshot | None) -> str:
    if state is None:
        return ""
    return state.state or ""


def state_to_dict(state: StateSnapshot | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "state": state.state,
        "attributes": state.attributes,
    }


def classify_incident_type(
    entity_id: str,
    old_state: StateSnapshot | None,
    new_state: StateSnapshot | None,
    *,
    monitored_domains: set[str],
    excluded_entities: set[str],
    battery_threshold: int,
    registry_device_class: str | None = None,
) -> str | None:
    if entity_id in excluded_entities:
        return None

    entity_domain = domain_for(entity_id)
    old = _state_value(old_state)
    new = _state_value(new_state)
    old_f = _float_or(old, 999)
    new_f = _float_or(new, 999)
    measure_new_f = _float_or(new, -999999)
    dc = _device_class(new_state, registry_device_class)

    if (
        entity_domain in monitored_domains
        and old not in INVALID_STATES
        and new in {"unavailable", "unknown"}
    ):
        return "state_change"

    if entity_domain in monitored_domains and new not in INVALID_STATES:
        if old in {"unavailable", "unknown"}:
            return "state_recovery"
        if old_state is None:
            return "state_recovery"
        if entity_domain == "sensor" and old in {"", "none"} and measure_new_f != -999999:
            return "state_recovery"

    if dc == "battery" and new_f < battery_threshold and old_f >= battery_threshold:
        return "battery_low"

    if dc == "battery" and new_f >= battery_threshold and old_f < battery_threshold:
        return "battery_recovered"

    if entity_domain in monitored_domains and new == "problem" and old != "problem":
        return "system_problem"

    if entity_domain in monitored_domains and old == "problem" and new != "problem":
        return "problem_cleared"

    if (
        entity_domain == "update"
        and new == "on"
        and old not in {"on", "unavailable", "unknown", "none", ""}
    ):
        return "update_available"

    if (
        entity_domain == "update"
        and old == "on"
        and new != "on"
        and new not in {"unavailable", "unknown", "none", ""}
    ):
        return "update_installed"

    return None


def build_state_change_payload(
    entity_id: str,
    old_state: StateSnapshot | None,
    new_state: StateSnapshot | None,
    *,
    monitored_domains: set[str],
    excluded_entities: set[str],
    battery_threshold: int,
    registry_device_class: str | None = None,
    registry_friendly_name: str | None = None,
    context: HaContext | None = None,
) -> IncidentPayload | None:
    incident_type = classify_incident_type(
        entity_id,
        old_state,
        new_state,
        monitored_domains=monitored_domains,
        excluded_entities=excluded_entities,
        battery_threshold=battery_threshold,
        registry_device_class=registry_device_class,
    )
    if not incident_type:
        return None

    entity_domain = domain_for(entity_id)
    friendly_name = entity_id
    if new_state and new_state.attributes.get("friendly_name"):
        friendly_name = str(new_state.attributes["friendly_name"])
    elif registry_friendly_name:
        friendly_name = registry_friendly_name

    dc = _device_class(new_state, registry_device_class)

    return IncidentPayload(
        incident_type=incident_type,
        entity_id=entity_id,
        friendly_name=friendly_name,
        domain=entity_domain,
        device_class=dc or "",
        state=str(_state_value(new_state)),
        details="",
        old_state=_state_value(old_state),
        new_state=state_to_dict(new_state),
        old_state_obj=state_to_dict(old_state),
        context=context or HaContext(),
    )


def build_repair_payload(
    event_data: dict[str, Any],
    *,
    context: HaContext | None = None,
) -> IncidentPayload:
    issue_id = str(event_data.get("issue_id", "unknown"))
    return IncidentPayload(
        incident_type="repair_event",
        entity_id=f"repairs.{issue_id}",
        friendly_name=f"HA Repair: {issue_id}",
        domain="repairs",
        device_class="",
        state="updated",
        details=json.dumps(event_data, separators=(",", ":")),
        context=context or HaContext(),
    )
