"""The Kinvia integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_event

from .const import (
    CONF_BATTERY_THRESHOLD,
    CONF_EXCLUDED_ENTITIES,
    CONF_MONITORED_DOMAINS,
    CONF_WEBHOOK_SECRET,
    DEFAULT_BATTERY_THRESHOLD,
    DEFAULT_MONITORED_DOMAINS,
    DOMAIN,
    EVENT_REPAIRS_UPDATED,
    EVENT_STATE_CHANGED,
)
from .incident import (
    IncidentPayload,
    StateSnapshot,
    build_repair_payload,
    build_state_change_payload,
)
from .webhook import KinviaWebhookClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


def _snapshot(state_obj: Any | None) -> StateSnapshot | None:
    if state_obj is None:
        return None
    return StateSnapshot(
        state=state_obj.state,
        attributes=dict(state_obj.attributes),
    )


class KinviaIncidentManager:
    """Listen to HA events and report incidents to Kinvia."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: KinviaWebhookClient,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def _config(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def _monitored_domains(self) -> set[str]:
        return set(self._config.get(CONF_MONITORED_DOMAINS, DEFAULT_MONITORED_DOMAINS))

    def _excluded_entities(self) -> set[str]:
        return set(self._config.get(CONF_EXCLUDED_ENTITIES, []))

    def _battery_threshold(self) -> int:
        return int(self._config.get(CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD))

    async def async_start(self) -> None:
        await self.client.async_start()
        self._unsubscribers.append(
            async_track_event(self.hass, EVENT_STATE_CHANGED, self._handle_state_changed)
        )
        self._unsubscribers.append(
            async_track_event(self.hass, EVENT_REPAIRS_UPDATED, self._handle_repair_event)
        )

    async def async_stop(self) -> None:
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers.clear()
        await self.client.async_stop()

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        if not entity_id:
            return

        registry = er.async_get(self.hass)
        reg_entry = registry.async_get(entity_id)
        registry_device_class = reg_entry.device_class if reg_entry else None
        registry_friendly_name = reg_entry.original_name if reg_entry else None

        payload = build_state_change_payload(
            entity_id,
            _snapshot(event.data.get("old_state")),
            _snapshot(event.data.get("new_state")),
            monitored_domains=self._monitored_domains(),
            excluded_entities=self._excluded_entities(),
            battery_threshold=self._battery_threshold(),
            registry_device_class=registry_device_class,
            registry_friendly_name=registry_friendly_name,
        )
        if payload:
            self.hass.async_create_task(self.client.async_enqueue(payload))

    @callback
    def _handle_repair_event(self, event: Event) -> None:
        payload = build_repair_payload(dict(event.data))
        self.hass.async_create_task(self.client.async_enqueue(payload))


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = KinviaWebhookClient(
        entry.data[CONF_URL],
        entry.data[CONF_WEBHOOK_SECRET],
    )
    manager = KinviaIncidentManager(hass, entry, client)
    await manager.async_start()
    hass.data[DOMAIN][entry.entry_id] = manager
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager: KinviaIncidentManager = hass.data[DOMAIN].pop(entry.entry_id)
    await manager.async_stop()
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
