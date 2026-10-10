"""Diagnostics support for the Chaster integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return privacy-conscious diagnostics without credentials or lock details."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    diagnostics: dict[str, Any] = {
        "config": {
            "token_configured": bool(entry.data.get(CONF_TOKEN)),
            "options": dict(entry.options),
        }
    }

    if coordinator is None:
        diagnostics["coordinator"] = {"loaded": False}
        return diagnostics

    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    diagnostics["coordinator"] = {
        "loaded": True,
        "last_update_success": coordinator.last_update_success,
        "last_api_response": coordinator.api.last_response_at,
        "last_api_error": coordinator.api.last_error,
        "rate_limit": dict(coordinator.api.rate_limit),
        "detected_roles": list(data.get("detected_roles") or []),
        "wearer_lock_count": len(coordinator._dict_list(data.get("locks"))),
        "shared_lock_count": len(coordinator._dict_list(data.get("shared_locks"))),
        "keyholder_lock_count": len(
            coordinator._dict_list(
                (data.get("keyholder") or {}).get("items")
                or (data.get("keyholder") or {}).get("locks")
                or (data.get("keyholder") or {}).get("results")
                or (data.get("keyholder") or {}).get("data")
            )
        ) if isinstance(data.get("keyholder"), dict) else 0,
        "conversation_count": len(coordinator._dict_list(data.get("conversations"))),
    }
    return diagnostics
