"""Config flow for Chaster using a developer/API token."""

from __future__ import annotations

from typing import Any, override

import probatio
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import ChasterApi, ChasterApiError
from .const import (
    CONF_ENABLE_KEYHOLDER,
    CONF_ENABLE_LOCK_ACTIONS,
    CONF_ENABLE_MESSAGING,
    CONF_ENABLE_SHARED_LOCKS,
    CONF_ROLE_MODE,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ROLE_AUTO,
    ROLE_BOTH,
    ROLE_KEYHOLDER,
    ROLE_WEARER,
)


class ChasterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Chaster developer-token authentication."""

    VERSION = 5

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for and validate a Chaster developer token."""
        return await self._async_token_form(user_input)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication after a token expires or is revoked."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Accept and validate a replacement developer token."""
        entry = self._get_reauth_entry()
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        if user_input is not None:
            token = str(user_input.get(CONF_TOKEN, "")).strip()
            if not token:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    data_schema=self._token_schema(),
                    errors={"base": "invalid_token"},
                )

            session = aiohttp_client.async_get_clientsession(self.hass)
            try:
                await ChasterApi(session, token=token).profile()
            except ChasterApiError:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    data_schema=self._token_schema(),
                    errors={"base": "cannot_connect"},
                )

            return self.async_update_reload_and_abort(
                entry,
                data_updates={CONF_TOKEN: token},
            )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self._token_schema(),
        )

    async def _async_token_form(
        self, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Validate a token and create the config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input.get(CONF_TOKEN, "")).strip()
            if not token:
                errors["base"] = "invalid_token"
            else:
                session = aiohttp_client.async_get_clientsession(self.hass)
                try:
                    await ChasterApi(session, token=token).profile()
                except ChasterApiError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title="Chaster",
                        data={CONF_TOKEN: token},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self._token_schema(),
            errors=errors,
            description_placeholders={
                "developers_url": "https://chaster.app/developers"
            },
        )

    @staticmethod
    def _token_schema() -> probatio.Schema:
        """Return the developer-token schema."""
        return probatio.Schema(
            {
                probatio.Required(CONF_TOKEN): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD,
                        autocomplete="current-password",
                    )
                )
            }
        )

    @staticmethod
    @override
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowWithReload:
        """Return Chaster's role and feature settings flow."""
        return ChasterOptionsFlow(config_entry)


class ChasterOptionsFlow(OptionsFlowWithReload):
    """Configure role-specific and optional Chaster features."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = self.config_entry.options
        schema = probatio.Schema(
            {
                probatio.Optional(
                    CONF_SCAN_INTERVAL,
                    default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): probatio.All(probatio.Coerce(int), probatio.Range(min=30, max=3600)),
                probatio.Optional(
                    CONF_ROLE_MODE,
                    default=defaults.get(CONF_ROLE_MODE, ROLE_AUTO),
                ): probatio.In(
                    [ROLE_AUTO, ROLE_WEARER, ROLE_KEYHOLDER, ROLE_BOTH]
                ),
                probatio.Optional(
                    CONF_ENABLE_KEYHOLDER,
                    default=defaults.get(CONF_ENABLE_KEYHOLDER, True),
                ): bool,
                probatio.Optional(
                    CONF_ENABLE_SHARED_LOCKS,
                    default=defaults.get(CONF_ENABLE_SHARED_LOCKS, True),
                ): bool,
                probatio.Optional(
                    CONF_ENABLE_MESSAGING,
                    default=defaults.get(CONF_ENABLE_MESSAGING, True),
                ): bool,
                probatio.Optional(
                    CONF_ENABLE_LOCK_ACTIONS,
                    default=defaults.get(CONF_ENABLE_LOCK_ACTIONS, True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
