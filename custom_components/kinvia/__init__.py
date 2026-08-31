"""The Kinvia integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, __version__ as HA_VERSION
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.start import async_at_started

from .const import (
    CONF_BATTERY_THRESHOLD,
    CONF_EXCLUDED_ENTITIES,
    CONF_MONITORED_DOMAINS,
    CONF_STARTUP_BASELINE,
    CONF_STARTUP_GRACE_MINUTES,
    CONF_WEBHOOK_SECRET,
    DEFAULT_BATTERY_THRESHOLD,
    DEFAULT_MONITORED_DOMAINS,
    DEFAULT_STARTUP_BASELINE,
    DEFAULT_STARTUP_GRACE_MINUTES,
    DOMAIN,
    EVENT_REPAIRS_UPDATED,
    EVENT_STATE_CHANGED,
    REPAIR_RECONCILE_INTERVAL_SECONDS,
)
from .incident import (
    HaContext,
    IncidentPayload,
    StateSnapshot,
    build_baseline_payload,
    build_repair_payload,
    build_state_change_payload,
    is_startup_suppressed_incident,
)
from .repair_sync import diff_repair_snapshots, repair_keys_from_registry
from .webhook import KinviaWebhookClient

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

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
        self._repair_snapshot: set[tuple[str, str]] = set()
        self._grace_active = False
        self._grace_unsub: Callable[[], None] | None = None
        self._at_started_unsub: Callable[[], None] | None = None
        self._skip_startup_grace = hass.state == CoreState.running

    @property
    def _config(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def _monitored_domains(self) -> set[str]:
        return set(self._config.get(CONF_MONITORED_DOMAINS, DEFAULT_MONITORED_DOMAINS))

    def _excluded_entities(self) -> set[str]:
        return set(self._config.get(CONF_EXCLUDED_ENTITIES, []))

    def _battery_threshold(self) -> int:
        return int(self._config.get(CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD))

    def _startup_grace_minutes(self) -> int:
        return int(
            self._config.get(CONF_STARTUP_GRACE_MINUTES, DEFAULT_STARTUP_GRACE_MINUTES)
        )

    def _startup_baseline_enabled(self) -> bool:
        return bool(self._config.get(CONF_STARTUP_BASELINE, DEFAULT_STARTUP_BASELINE))

    def _ha_context(self, entity_id: str | None = None) -> HaContext:
        location = self.hass.config.location_name or ""
        timezone = str(self.hass.config.time_zone)
        if not entity_id:
            return HaContext(
                ha_version=HA_VERSION,
                ha_location=location or None,
                ha_timezone=timezone or None,
            )

        entity_registry = er.async_get(self.hass)
        reg_entry = entity_registry.async_get(entity_id)
        if not reg_entry:
            return HaContext(
                ha_version=HA_VERSION,
                ha_location=location or None,
                ha_timezone=timezone or None,
            )

        entity_registry_payload: dict[str, str] = {}
        if reg_entry.platform:
            entity_registry_payload["platform"] = reg_entry.platform
        if reg_entry.config_entry_id:
            entity_registry_payload["config_entry_id"] = reg_entry.config_entry_id
        if reg_entry.device_id:
            entity_registry_payload["device_id"] = reg_entry.device_id
        if reg_entry.area_id:
            entity_registry_payload["area_id"] = reg_entry.area_id

        device_payload: dict[str, str] | None = None
        area_id = reg_entry.area_id
        if reg_entry.device_id:
            device_registry = dr.async_get(self.hass)
            device_entry = device_registry.async_get(reg_entry.device_id)
            if device_entry:
                device_payload = {"id": device_entry.id}
                if device_entry.name:
                    device_payload["name"] = device_entry.name
                if device_entry.manufacturer:
                    device_payload["manufacturer"] = device_entry.manufacturer
                if device_entry.model:
                    device_payload["model"] = device_entry.model
                if device_entry.sw_version:
                    device_payload["sw_version"] = device_entry.sw_version
                if device_entry.hw_version:
                    device_payload["hw_version"] = device_entry.hw_version
                if not area_id and device_entry.area_id:
                    area_id = device_entry.area_id

        area_payload: dict[str, str] | None = None
        if area_id:
            area_registry = ar.async_get(self.hass)
            area_entry = area_registry.async_get_area(area_id)
            if area_entry:
                area_payload = {"id": area_entry.id}
                if area_entry.name:
                    area_payload["name"] = area_entry.name

        return HaContext(
            ha_version=HA_VERSION,
            ha_location=location or None,
            ha_timezone=timezone or None,
            device=device_payload,
            area=area_payload,
            entity_registry=entity_registry_payload or None,
        )

    async def async_start(self) -> None:
        await self.client.async_start()
        self._repair_snapshot = repair_keys_from_registry(self.hass)
        self._at_started_unsub = async_at_started(self.hass, self._async_enable_monitoring)

    async def async_stop(self) -> None:
        if self._at_started_unsub is not None:
            self._at_started_unsub()
            self._at_started_unsub = None
        if self._grace_unsub is not None:
            self._grace_unsub()
            self._grace_unsub = None
        self._grace_active = False
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers.clear()
        await self.client.async_stop()

    @callback
    def _async_enable_monitoring(self, _hass: HomeAssistant) -> None:
        """Subscribe to HA events once Home Assistant has finished starting."""
        self._unsubscribers.append(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed)
        )
        self._unsubscribers.append(
            self.hass.bus.async_listen(EVENT_REPAIRS_UPDATED, self._handle_repair_event)
        )
        self._unsubscribers.append(
            async_track_time_interval(
                self.hass,
                self._async_reconcile_repairs,
                timedelta(seconds=REPAIR_RECONCILE_INTERVAL_SECONDS),
            )
        )

        grace_minutes = self._startup_grace_minutes()
        if self._skip_startup_grace or grace_minutes <= 0:
            return

        self._grace_active = True
        _LOGGER.info(
            "Kinvia startup grace period active for %d minutes "
            "(suppressing state_change and state_recovery incidents)",
            grace_minutes,
        )
        self._grace_unsub = async_call_later(
            self.hass,
            timedelta(minutes=grace_minutes),
            self._async_finish_startup_grace_callback,
        )

    @callback
    def _async_finish_startup_grace_callback(self, _now: Any) -> None:
        self.hass.async_create_task(self._async_finish_startup_grace())

    async def _async_finish_startup_grace(self) -> None:
        was_grace = self._grace_active
        self._grace_active = False
        if self._grace_unsub is not None:
            self._grace_unsub()
            self._grace_unsub = None

        if was_grace:
            _LOGGER.info("Kinvia startup grace period ended")

        if was_grace and self._startup_baseline_enabled():
            await self._async_emit_baseline()

    async def _async_emit_baseline(self) -> None:
        """Report entities already in a problematic state after startup settles."""
        registry = er.async_get(self.hass)
        payloads: list[IncidentPayload] = []

        for state in self.hass.states.async_all():
            entity_id = state.entity_id
            reg_entry = registry.async_get(entity_id)
            snapshot = _snapshot(state)
            if snapshot is None:
                continue

            payload = build_baseline_payload(
                entity_id,
                snapshot,
                monitored_domains=self._monitored_domains(),
                excluded_entities=self._excluded_entities(),
                battery_threshold=self._battery_threshold(),
                registry_device_class=reg_entry.device_class if reg_entry else None,
                registry_friendly_name=reg_entry.original_name if reg_entry else None,
                context=self._ha_context(entity_id),
            )
            if payload:
                payloads.append(payload)

        if not payloads:
            _LOGGER.debug("Kinvia startup baseline: no problematic entities found")
            return

        _LOGGER.info(
            "Kinvia startup baseline: reporting %d entities in a problematic state",
            len(payloads),
        )
        for payload in payloads:
            await self.client.async_enqueue(payload)

    def _should_report_state_incident(self, payload: IncidentPayload) -> bool:
        if self._grace_active and is_startup_suppressed_incident(payload.incident_type):
            return False
        return True

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
            context=self._ha_context(entity_id),
        )
        if payload and self._should_report_state_incident(payload):
            self.hass.async_create_task(self.client.async_enqueue(payload))

    @callback
    def _handle_repair_event(self, event: Event) -> None:
        event_data = dict(event.data)
        action = event_data.get("action")
        domain = str(event_data.get("domain", "unknown"))
        issue_id = str(event_data.get("issue_id", "unknown"))
        repair_key = (domain, issue_id)

        if action == "remove":
            self._repair_snapshot.discard(repair_key)
        elif action in ("create", "update"):
            self._repair_snapshot.add(repair_key)

        _LOGGER.info(
            "Kinvia repair event: action=%s domain=%s issue_id=%s",
            action,
            domain,
            issue_id,
        )

        payload = build_repair_payload(
            event_data,
            context=self._ha_context(),
        )
        self.hass.async_create_task(self.client.async_enqueue(payload))

    @callback
    def _async_reconcile_repairs(self, _now: Any) -> None:
        """Detect repairs removed from HA without a bus event (missed webhook path)."""
        current = repair_keys_from_registry(self.hass)
        added, removed = diff_repair_snapshots(self._repair_snapshot, current)
        self._repair_snapshot = current

        if not added and not removed:
            return

        _LOGGER.info(
            "Kinvia repair reconcile: %d added, %d removed",
            len(added),
            len(removed),
        )

        for domain, issue_id in removed:
            payload = build_repair_payload(
                {"action": "remove", "domain": domain, "issue_id": issue_id},
                context=self._ha_context(),
            )
            self.hass.async_create_task(self.client.async_enqueue(payload))

        for domain, issue_id in added:
            payload = build_repair_payload(
                {"action": "create", "domain": domain, "issue_id": issue_id},
                context=self._ha_context(),
            )
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
