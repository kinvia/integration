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
    CONF_WEBHOOK_SECRET,
    DEFAULT_BATTERY_THRESHOLD,
    DEFAULT_MONITORED_DOMAINS,
    DOMAIN,
)
from .webhook import validate_connection


def _normalize_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid_url")
    return cleaned


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
            try:
                url = _normalize_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            else:
                webhook_secret = user_input[CONF_WEBHOOK_SECRET].strip()
                if not webhook_secret:
                    errors[CONF_WEBHOOK_SECRET] = "invalid_auth"
                else:
                    try:
                        async with aiohttp.ClientSession() as session:
                            result = await validate_connection(
                                url, webhook_secret, session=session
                            )
                    except aiohttp.ClientError:
                        errors["base"] = "cannot_connect"
                    else:
                        status = result["status"]
                        if result.get("step") == "server" and status >= 400:
                            errors["base"] = "cannot_connect"
                        elif status == 401:
                            errors[CONF_WEBHOOK_SECRET] = "invalid_auth"
                        elif status >= 400:
                            errors["base"] = "cannot_connect"
                        else:
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
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MONITORED_DOMAINS,
                        default=DEFAULT_MONITORED_DOMAINS,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=DEFAULT_MONITORED_DOMAINS,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_EXCLUDED_ENTITIES, default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Required(
                        CONF_BATTERY_THRESHOLD,
                        default=DEFAULT_BATTERY_THRESHOLD,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            mode=selector.NumberSelectorMode.SLIDER,
                            unit_of_measurement="%",
                        )
                    ),
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
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MONITORED_DOMAINS,
                        default=data.get(CONF_MONITORED_DOMAINS, DEFAULT_MONITORED_DOMAINS),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=DEFAULT_MONITORED_DOMAINS,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_EXCLUDED_ENTITIES,
                        default=data.get(CONF_EXCLUDED_ENTITIES, []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Required(
                        CONF_BATTERY_THRESHOLD,
                        default=data.get(CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            mode=selector.NumberSelectorMode.SLIDER,
                            unit_of_measurement="%",
                        )
                    ),
                }
            ),
        )
