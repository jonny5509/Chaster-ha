from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChasterCoordinator


class ChasterEntity(CoordinatorEntity):
    """Base entity for a Chaster role device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ChasterCoordinator, role: str | None = None) -> None:
        super().__init__(coordinator)
        self.role = role

    @property
    def device_info(self):
        profile = self.coordinator.data.get("profile", {})
        username = profile.get("username") if isinstance(profile, dict) else None
        entry_id = self.coordinator.config_entry.entry_id

        if self.role == "wearer":
            return DeviceInfo(
                identifiers={(DOMAIN, entry_id, "wearer")},
                name="Chaster - My lock",
                manufacturer="Chaster",
                model="My lock",
            )
        if self.role == "keyholder":
            return DeviceInfo(
                identifiers={(DOMAIN, entry_id, "keyholder")},
                name="Chaster - Keyholder",
                manufacturer="Chaster",
                model="Keyholder",
            )

        return DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=f"Chaster - {username}" if username else "Chaster",
            manufacturer="Chaster",
            model="Chaster account",
        )
