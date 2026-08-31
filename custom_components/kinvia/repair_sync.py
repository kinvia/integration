"""Repair registry snapshot diffing for missed create/remove events."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

RepairKey = tuple[str, str]


def repair_keys_from_registry(hass: HomeAssistant) -> set[RepairKey]:
    """Return all (domain, issue_id) pairs currently in the HA issue registry."""
    from homeassistant.helpers import issue_registry as ir

    registry = ir.async_get(hass)
    return set(registry.issues.keys())


def diff_repair_snapshots(
    previous: set[RepairKey],
    current: set[RepairKey],
) -> tuple[set[RepairKey], set[RepairKey]]:
    """Return (added, removed) repair keys between two snapshots."""
    return current - previous, previous - current
