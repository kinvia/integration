"""Config flow for the Kinvia integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

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
)
from .webhook import validate_connection


def _normalize_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid_url")
    return cleaned


async def _async_validate_credentials(
    raw_url: str, raw_secret: str
) -> tuple[dict[str, str], str | None, str | None]:
    """Validate URL and webhook secret. Returns errors and normalized values."""
    errors: dict[str, str] = {}
    try:
        url = _normalize_url(raw_url)
    except ValueError:
        return {CONF_URL: "invalid_url"}, None, None

    webhook_secret = raw_secret.strip()
    if not webhook_secret:
        return {CONF_WEBHOOK_SECRET: "invalid_auth"}, None, None

    try:
        async with aiohttp.ClientSession() as session:
            result = await validate_connection(url, webhook_secret, session=session)
    except aiohttp.ClientError:
        return {"base": "cannot_connect"}, None, None

    status = result["status"]
    if result.get("step") == "server" and status >= 400:
        errors["base"] = "cannot_connect"
    elif status == 401:
        errors[CONF_WEBHOOK_SECRET] = "invalid_auth"
    elif status >= 400:
        errors["base"] = "cannot_connect"

    if errors:
        return errors, None, None
    return {}, url, webhook_secret


def _is_url_available(
    hass: HomeAssistant, entry_id: str, url: str
) -> bool:
    """Return False if another entry already uses this URL."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != entry_id and entry.unique_id == url:
            return False
    return True


def _monitoring_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_MONITORED_DOMAINS,
                default=defaults.get(CONF_MONITORED_DOMAINS, DEFAULT_MONITORED_DOMAINS),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DEFAULT_MONITORED_DOMAINS,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_EXCLUDED_ENTITIES,
                default=defaults.get(CONF_EXCLUDED_ENTITIES, []),
            ): selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
            vol.Required(
                CONF_BATTERY_THRESHOLD,
                default=defaults.get(CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=100,
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_STARTUP_GRACE_MINUTES,
                default=defaults.get(
                    CONF_STARTUP_GRACE_MINUTES, DEFAULT_STARTUP_GRACE_MINUTES
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=60,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Required(
                CONF_STARTUP_BASELINE,
                default=defaults.get(CONF_STARTUP_BASELINE, DEFAULT_STARTUP_BASELINE),
            ): selector.BooleanSelector(),
        }
    )


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=defaults.get(CONF_URL, "")): selector.TextSelector(),
            vol.Required(
                CONF_WEBHOOK_SECRET, default=defaults.get(CONF_WEBHOOK_SECRET, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            **_monitoring_options_schema(defaults).schema,
        }
    )


class KinviaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kinvia."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, url, webhook_secret = await _async_validate_credentials(
                user_input[CONF_URL], user_input[CONF_WEBHOOK_SECRET]
            )
            if not errors and url and webhook_secret:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                self._user_input = {
                    CONF_URL: url,
                    CONF_WEBHOOK_SECRET: webhook_secret,
                }
                return await self.async_step_init()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL): selector.TextSelector(),
                    vol.Required(CONF_WEBHOOK_SECRET): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Kinvia",
                data={
                    **self._user_input,
                    CONF_MONITORED_DOMAINS: user_input[CONF_MONITORED_DOMAINS],
                    CONF_EXCLUDED_ENTITIES: user_input[CONF_EXCLUDED_ENTITIES],
                    CONF_BATTERY_THRESHOLD: user_input[CONF_BATTERY_THRESHOLD],
                    CONF_STARTUP_GRACE_MINUTES: user_input[CONF_STARTUP_GRACE_MINUTES],
                    CONF_STARTUP_BASELINE: user_input[CONF_STARTUP_BASELINE],
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_monitoring_options_schema(
                {
                    CONF_MONITORED_DOMAINS: DEFAULT_MONITORED_DOMAINS,
                    CONF_EXCLUDED_ENTITIES: [],
                    CONF_BATTERY_THRESHOLD: DEFAULT_BATTERY_THRESHOLD,
                    CONF_STARTUP_GRACE_MINUTES: DEFAULT_STARTUP_GRACE_MINUTES,
                    CONF_STARTUP_BASELINE: DEFAULT_STARTUP_BASELINE,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> KinviaOptionsFlow:
        return KinviaOptionsFlow()


class KinviaOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Kinvia."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        defaults = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            errors, url, webhook_secret = await _async_validate_credentials(
                user_input[CONF_URL], user_input[CONF_WEBHOOK_SECRET]
            )
            if (
                not errors
                and url
                and webhook_secret
                and not _is_url_available(self.hass, self.config_entry.entry_id, url)
            ):
                errors["base"] = "already_configured"

            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_options_schema(defaults),
                    errors=errors,
                )

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_URL: url,
                    CONF_WEBHOOK_SECRET: webhook_secret,
                },
                unique_id=url,
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_MONITORED_DOMAINS: user_input[CONF_MONITORED_DOMAINS],
                    CONF_EXCLUDED_ENTITIES: user_input[CONF_EXCLUDED_ENTITIES],
                    CONF_BATTERY_THRESHOLD: user_input[CONF_BATTERY_THRESHOLD],
                    CONF_STARTUP_GRACE_MINUTES: user_input[CONF_STARTUP_GRACE_MINUTES],
                    CONF_STARTUP_BASELINE: user_input[CONF_STARTUP_BASELINE],
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(defaults),
        )
