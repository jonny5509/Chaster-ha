"""Config flow for Chaster using a developer/API token."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, selector

from .api import ChasterApi, ChasterApiError
from .const import (
    CONF_ENABLE_KEYHOLDER,
    CONF_ENABLE_LOCK_ACTIONS,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_ENABLE_PHONE_NOTIFICATIONS,
    CONF_ENABLE_HA_NOTIFICATIONS,
    CONF_NOTIFICATION_DESTINATION,
    CONF_NOTIFICATION_TARGETS,
    CONF_NOTIFICATION_SERVICE,
    CONF_NOTIFY_DAILY,
    CONF_NOTIFY_COMPLETION,
    CONF_NOTIFY_WEARER,
    CONF_NOTIFY_KEYHOLDER,
    CONF_NOTIFY_HA_DAILY,
    CONF_NOTIFY_HA_COMPLETION,
    DEFAULT_NOTIFICATION_SERVICE,
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

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Ask for and validate a Chaster developer token."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        return await self._async_token_form(user_input, reauth_entry=None)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> Any:
        """Handle reauthentication after a token expires or is revoked."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_failed")
        self._reauth_entry = entry
        return await self._async_token_form(None, reauth_entry=entry)

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> Any:
        """Accept and validate a replacement developer token."""
        entry = getattr(self, "_reauth_entry", None)
        if entry is None:
            return self.async_abort(reason="reauth_failed")
        return await self._async_token_form(user_input, reauth_entry=entry)

    async def _async_token_form(self, user_input, reauth_entry):
        """Validate a token and either create or update the config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input.get(CONF_TOKEN, "")).strip()
            if not token:
                errors["base"] = "invalid_token"
            else:
                session = aiohttp_client.async_get_clientsession(self.hass)
                try:
                    profile = await ChasterApi(session, token=token).profile()
                except ChasterApiError as err:
                    message = str(err)
                    if "HTTP 401" in message or "HTTP 403" in message:
                        errors["base"] = "invalid_auth"
                    else:
                        errors["base"] = "cannot_connect"
                else:
                    if reauth_entry is not None:
                        self.hass.config_entries.async_update_entry(
                            reauth_entry, data={**reauth_entry.data, CONF_TOKEN: token}
                        )
                        await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                        return self.async_abort(reason="reauth_successful")
                    username = (
                        profile.get("username")
                        if isinstance(profile, dict)
                        else None
                    )
                    title = f"Chaster - {username}" if isinstance(username, str) and username.strip() else "Chaster"
                    return self.async_create_entry(title=title, data={CONF_TOKEN: token})

        step_id = "reauth_confirm" if reauth_entry is not None else "user"
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
            description_placeholders={"developers_url": "https://chaster.app/developers"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return Chaster's role and feature settings flow."""
        return ChasterOptionsFlow()


class ChasterOptionsFlow(config_entries.OptionsFlow):
    """Configure role-specific and optional Chaster features."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = self.config_entry.options
        # Match EmlaLock: phone targets must be Companion App mobile_app services.
        notify_services = sorted(
            name
            for name in self.hass.services.async_services().get("notify", {})
            if name.startswith("mobile_app_")
        )
        service_options = [
            {
                "value": f"notify.{name}",
                "label": name.removeprefix("mobile_app_").replace("_", " "),
            }
            for name in notify_services
        ]
        # Preserve saved targets if service discovery is temporarily incomplete.
        for target in defaults.get(CONF_NOTIFICATION_TARGETS, []):
            service_name = str(target).removeprefix("notify.")
            if service_name.startswith("mobile_app_") and all(
                item["value"] != f"notify.{service_name}" for item in service_options
            ):
                service_options.append({
                    "value": f"notify.{service_name}",
                    "label": service_name.removeprefix("mobile_app_").replace("_", " "),
                })
        destination = defaults.get(CONF_NOTIFICATION_DESTINATION)
        if destination not in {"none", "home_assistant", "phone", "both"}:
            phone = defaults.get(CONF_ENABLE_PHONE_NOTIFICATIONS, False)
            ha = defaults.get(CONF_ENABLE_HA_NOTIFICATIONS, False)
            destination = "both" if phone and ha else "phone" if phone else "home_assistant" if ha else "none"
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
                    vol.Optional(CONF_ROLE_MODE, default=defaults.get(CONF_ROLE_MODE, ROLE_AUTO)): vol.In([ROLE_AUTO, ROLE_WEARER, ROLE_KEYHOLDER, ROLE_BOTH]),
                    vol.Optional(CONF_ENABLE_KEYHOLDER, default=defaults.get(CONF_ENABLE_KEYHOLDER, True)): bool,
                    vol.Optional(CONF_ENABLE_SHARED_LOCKS, default=defaults.get(CONF_ENABLE_SHARED_LOCKS, True)): bool,
                    vol.Optional(CONF_ENABLE_MESSAGING, default=defaults.get(CONF_ENABLE_MESSAGING, True)): bool,
                    vol.Optional(CONF_ENABLE_LOCK_ACTIONS, default=defaults.get(CONF_ENABLE_LOCK_ACTIONS, True)): bool,
                    vol.Optional(
                        CONF_NOTIFICATION_DESTINATION,
                        default=defaults.get(
                            CONF_NOTIFICATION_DESTINATION,
                            "both" if defaults.get(CONF_ENABLE_PHONE_NOTIFICATIONS, False) and defaults.get(CONF_ENABLE_HA_NOTIFICATIONS, False)
                            else "phone" if defaults.get(CONF_ENABLE_PHONE_NOTIFICATIONS, False)
                            else "home_assistant" if defaults.get(CONF_ENABLE_HA_NOTIFICATIONS, False)
                            else "none",
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"label": "None", "value": "none"},
                                {"label": "Home Assistant notifications", "value": "home_assistant"},
                                {"label": "Phone notifications", "value": "phone"},
                                {"label": "Home Assistant and phone", "value": "both"},
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_NOTIFICATION_TARGETS,
                        default=defaults.get(CONF_NOTIFICATION_TARGETS, []),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=service_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_NOTIFY_WEARER, default=defaults.get(CONF_NOTIFY_WEARER, False)): bool,
                    vol.Optional(CONF_NOTIFY_KEYHOLDER, default=defaults.get(CONF_NOTIFY_KEYHOLDER, False)): bool,
                }
            ),
        )
