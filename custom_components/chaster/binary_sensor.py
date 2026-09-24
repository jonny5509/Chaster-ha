from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity

from .coordinator import ChasterCoordinator
from .entity import ChasterEntity


class _CurrentLockBinary(ChasterEntity, BinarySensorEntity):
    def __init__(self, coordinator, role, suffix, name, icon):
        super().__init__(coordinator, role)
        self._suffix = suffix
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{role}_{suffix}"

    @property
    def _lock(self):
        if self.role == "wearer":
            locks = self.coordinator.data.get("locks", [])
        else:
            data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
            keyholder = data.get("keyholder", {})
            items = keyholder.get("items") or keyholder.get("locks") or keyholder.get("results") or keyholder.get("data") or []
            if isinstance(items, dict):
                items = list(items.values())
            locks = []
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict):
                    lock = item.get("lock") if isinstance(item.get("lock"), dict) else item
                    if isinstance(lock, dict):
                        locks.append(lock)
        active = [x for x in locks if isinstance(x, dict) and self.coordinator.lock_id(x) and self.coordinator.is_active(x)]
        return max(active, key=lambda x: str(x.get("startDate") or x.get("startAt") or x.get("createdAt") or ""), default={})

    @property
    def extra_state_attributes(self):
        lock = self._lock
        return {
            "lock_id": self.coordinator.lock_id(lock),
            "role": self.role,
            "status": lock.get("status"),
            "type": lock.get("type"),
        }


class ChasterLockedBinary(_CurrentLockBinary):
    def __init__(self, coordinator, role):
        super().__init__(coordinator, role, "locked", "Locked", "mdi:lock")

    @property
    def is_on(self):
        return self.coordinator.is_active(self._lock)


class ChasterFrozenBinary(_CurrentLockBinary):
    def __init__(self, coordinator, role):
        super().__init__(coordinator, role, "frozen", "Frozen", "mdi:snowflake")

    @property
    def is_on(self):
        lock = self._lock
        return bool(lock.get("frozen", lock.get("isFrozen", False)))


class ChasterTestBinary(_CurrentLockBinary):
    def __init__(self, coordinator, role):
        super().__init__(coordinator, role, "test_lock", "Test lock", "mdi:flask-outline")

    @property
    def is_on(self):
        lock = self._lock
        return bool(lock.get("isTestLock") or lock.get("test") or lock.get("isTest") or lock.get("testLock", False))


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: ChasterCoordinator = hass.data[entry.domain][entry.entry_id]
    entities = []
    for role in ("wearer", "keyholder"):
        entities.extend([
            ChasterLockedBinary(coordinator, role),
            ChasterFrozenBinary(coordinator, role),
            ChasterTestBinary(coordinator, role),
        ])
    async_add_entities(entities)
