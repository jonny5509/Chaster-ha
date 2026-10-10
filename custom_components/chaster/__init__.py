from __future__ import annotations

import re
import voluptuous as vol
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .api import ChasterApi, ChasterApiError
from .const import (
    CONF_ENABLE_KEYHOLDER,
    CONF_ENABLE_LOCK_ACTIONS,
    CONF_ENABLE_MESSAGING,
    CONF_ENABLE_SHARED_LOCKS,
    CONF_ROLE_MODE,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DOMAIN,
    PLATFORMS,
    ROLE_AUTO,
)
from .coordinator import ChasterCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Keep the generic service read-only. Mutations should use the narrowly scoped
# lock_action/add_time/remove_time/send_message services instead.
_READ_ONLY_PATHS = {
    "/auth/profile",
    "/locks",
    "/shared-locks",
    "/conversations",
    "/permissions/definitions",
}
_ID = r"[A-Za-z0-9_-]+"
_READ_ONLY_PATH_PATTERNS = (
    re.compile(rf"/locks/{_ID}"),
    re.compile(rf"/conversations/{_ID}"),
    re.compile(rf"/keyholder/notes/lock/{_ID}"),
)
_LOCK_ACTION_PATHS = {
    "/locks/{lock_id}/freeze",
    "/locks/{lock_id}/archive",
    "/locks/{lock_id}/archive/keyholder",
    "/locks/{lock_id}/settings",
    "/locks/{lock_id}/bondage-config",
}
_LOCK_EXTENSION_ACTION = re.compile(rf"/locks/{_ID}/extensions/{_ID}/action")
_CONVERSATION_PATH = re.compile(rf"/conversations(?:/{_ID})?")


def _validate_api_path(path: str) -> str:
    """Reject paths that could escape the intended Chaster API endpoint."""
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "\\" in path
        or "?" in path
        or "#" in path
        or any(part in {".", ".."} for part in path.split("/"))
        or re.search(r"%2e|%2f|%5c", path, re.IGNORECASE)
    ):
        raise HomeAssistantError("Invalid Chaster API path")
    return path


def _coordinators(hass: HomeAssistant) -> list[ChasterCoordinator]:
    """Return configured Chaster coordinators."""
    return [value for value in hass.data[DOMAIN].values() if isinstance(value, ChasterCoordinator)]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register Chaster services."""
    hass.data.setdefault(DOMAIN, {})
    card_file = Path(__file__).resolve().parent / "www" / "chaster-card.js"
    if card_file.is_file():
        await hass.http.async_register_static_paths([StaticPathConfig("/chaster/chaster-card.js", str(card_file), cache_headers=False)])
        frontend.add_extra_js_url(hass, "/chaster/chaster-card.js")

    async def _api_for_lock(lock_id: str):
        for coordinator in _coordinators(hass):
            if any(coordinator.lock_id(item) == lock_id for item in coordinator.all_locks):
                return coordinator.api, coordinator
        raise HomeAssistantError(f"Chaster lock {lock_id} is not known to this Home Assistant instance")

    async def api_request(call: ServiceCall) -> None:
        coordinators = _coordinators(hass)
        if not coordinators:
            raise HomeAssistantError("No Chaster account is configured")
        path = _validate_api_path(call.data["path"])
        if call.data["method"] != "GET" or not (
            path in _READ_ONLY_PATHS
            or any(pattern.fullmatch(path) for pattern in _READ_ONLY_PATH_PATTERNS)
        ):
            raise HomeAssistantError(
                "api_request is read-only and only supports documented account, lock, "
                "conversation, and permission lookup paths"
            )
        result = await coordinators[0].api.request(
            "GET", path, params=call.data.get("params")
        )
        hass.bus.async_fire(
            f"{DOMAIN}_api_response",
            {"method": "GET", "path": path, "result": result},
        )
        for coordinator in coordinators:
            await coordinator.async_request_refresh()

    async def lock_action(call: ServiceCall) -> None:
        lock_id = call.data["lock_id"]
        if not re.fullmatch(_ID, lock_id):
            raise HomeAssistantError("Invalid Chaster lock ID")
        api, coordinator = await _api_for_lock(lock_id)
        if not coordinator.enable_lock_actions:
            raise HomeAssistantError("Lock actions are disabled in integration options")
        template = call.data["path"]
        path = template.format(lock_id=lock_id)
        if template not in _LOCK_ACTION_PATHS and not re.fullmatch(
            rf"/locks/{re.escape(lock_id)}/extensions/{_ID}/action", path
        ):
            raise HomeAssistantError("Unsupported Chaster lock action path")
        _validate_api_path(path)
        result = await api.request(call.data.get("method", "POST"), path, json=call.data.get("body", {}))
        hass.bus.async_fire(
            f"{DOMAIN}_action",
            {"lock_id": lock_id, "path": path, "result": result},
        )
        await coordinator.async_request_refresh()

    async def add_or_remove_time(call: ServiceCall) -> None:
        api, coordinator = await _api_for_lock(call.data["lock_id"])
        if not coordinator.enable_lock_actions:
            raise HomeAssistantError("Lock actions are disabled in integration options")
        seconds = int(call.data["seconds"])
        result = await api.update_time(
            call.data["lock_id"], seconds if call.service == "add_time" else -seconds
        )
        hass.bus.async_fire(
            f"{DOMAIN}_action",
            {"lock_id": call.data["lock_id"], "action": call.service, "seconds": seconds, "result": result},
        )
        await coordinator.async_request_refresh()

    async def send_message(call: ServiceCall) -> None:
        coordinators = _coordinators(hass)
        if not coordinators:
            raise HomeAssistantError("No Chaster account is configured")
        path = _validate_api_path(call.data.get("path", "/conversations"))
        if not _CONVERSATION_PATH.fullmatch(path):
            raise HomeAssistantError("send_message only supports Chaster conversation endpoints")
        coordinator = coordinators[0]
        if not coordinator.enable_messaging:
            raise HomeAssistantError("Messaging is disabled in integration options")
        result = await coordinator.api.request("POST", path, json=call.data["body"])
        hass.bus.async_fire(f"{DOMAIN}_message", {"result": result})

    hass.services.async_register(
        DOMAIN,
        "api_request",
        api_request,
        schema=vol.Schema(
            {
                vol.Required("method"): vol.In(["GET"]),
                vol.Required("path"): str,
                vol.Optional("params"): dict,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "lock_action",
        lock_action,
        schema=vol.Schema(
            {
                vol.Required("lock_id"): str,
                vol.Required("path"): str,
                vol.Optional("method", default="POST"): vol.In(["POST", "PUT", "PATCH", "DELETE"]),
                vol.Optional("body"): dict,
            }
        ),
    )
    time_schema = vol.Schema(
        {
            vol.Required("lock_id"): str,
            vol.Required("seconds"): vol.All(vol.Coerce(int), vol.Range(min=1, max=31_536_000)),
        }
    )
    hass.services.async_register(DOMAIN, "add_time", add_or_remove_time, schema=time_schema)
    hass.services.async_register(DOMAIN, "remove_time", add_or_remove_time, schema=time_schema)
    hass.services.async_register(
        DOMAIN,
        "send_message",
        send_message,
        schema=vol.Schema({vol.Required("body"): dict, vol.Optional("path", default="/conversations"): str}),
    )
    return True


async def _remove_legacy_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove every Chaster entity that is not in the requested sensor list."""
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"

    allowed_suffixes = {
        "wearer_username", "my_lock_keyholder_username", "wearer_lock_title",
        "keyholder_lock_title", "my_lock_time_locked", "keyholder_time_locked",
        "my_lock_time_remaining", "keyholder_time_remaining", "my_lock_max_time_remaining",
        "keyholder_max_time_remaining", "my_lock_session_role", "keyholder_session_role",
        "my_lock_task_points", "keyholder_task_points", "my_lock_task_points_required",
        "keyholder_task_points_required", "my_lock_task_points_remaining",
        "keyholder_task_points_remaining", "keyholder_device_wearer_username",
        "wearer_locked", "keyholder_locked", "wearer_ready_to_unlock",
        "keyholder_ready_to_unlock", "wearer_frozen", "keyholder_frozen",
        "wearer_task_assigned", "keyholder_task_assigned", "sessions_calendar",
    }

    for entity in list(registry.entities.values()):
        if entity.config_entry_id != entry.entry_id:
            continue
        unique_id = (entity.unique_id or "").lower()
        if unique_id.startswith(prefix):
            suffix = unique_id[len(prefix):]
            if suffix not in allowed_suffixes:
                registry.async_remove(entity.entity_id)
            continue

        # Remove old entities whose unique IDs were not based on the config entry ID.
        original_name = (entity.original_name or "").lower()
        name = (entity.name or "").lower()
        if any(
            marker in original_name or marker in name
            for marker in (
                "obedience connected", "current lock history", "keyholder lock",
                "my lock -", "shared lock -",
            )
        ):
            registry.async_remove(entity.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Chaster config entry."""
    await _remove_legacy_entities(hass, entry)
    session = aiohttp_client.async_get_clientsession(hass)
    token = entry.data.get(CONF_TOKEN)
    if not isinstance(token, str) or not token.strip():
        raise ConfigEntryNotReady("No Chaster developer token is configured")

    api = ChasterApi(session, token=token.strip())
    settings = entry.options
    try:
        await api.profile()
    except ChasterApiError as err:
        message = str(err)
        if "HTTP 401" in message or "HTTP 403" in message:
            raise ConfigEntryAuthFailed("Chaster developer token is invalid or expired") from err
        raise ConfigEntryNotReady(f"Unable to connect to Chaster: {err}") from err

    coordinator = ChasterCoordinator(
        hass,
        api,
        settings.get(CONF_SCAN_INTERVAL, 60),
        role_mode=settings.get(CONF_ROLE_MODE, ROLE_AUTO),
        enable_keyholder=settings.get(CONF_ENABLE_KEYHOLDER, True),
        enable_shared=settings.get(CONF_ENABLE_SHARED_LOCKS, True),
        enable_messaging=settings.get(CONF_ENABLE_MESSAGING, True),
        enable_lock_actions=settings.get(CONF_ENABLE_LOCK_ACTIONS, True),
    )
    coordinator.config_entry = entry
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Chaster config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if unload_ok and not _coordinators(hass):
        for service in ("api_request", "lock_action", "add_time", "remove_time", "send_message"):
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok
