from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers import entity_registry as er

from .coordinator import ChasterCoordinator
from .entity import ChasterEntity


def _id(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in ("id", "_id", "lockId", "lock_id", "sessionId", "session_id"):
        value = item.get(key)
        if value is not None:
            return str(value)
    nested = item.get("lock")
    return _id(nested) if isinstance(nested, dict) else None


def _name(item: Any) -> str:
    if not isinstance(item, dict):
        return "Lock"
    return str(item.get("customWearerName") or item.get("name") or item.get("title") or _id(item) or "Lock")


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (TypeError, ValueError):
            return None
    return None


def _duration_seconds(value: Any) -> int | None:
    direct = _number(value)
    if direct is not None:
        return direct
    if isinstance(value, dict):
        for key in ("seconds", "totalSeconds", "remainingSeconds", "value", "duration", "total", "amount"):
            result = _duration_seconds(value.get(key))
            if result is not None:
                return result
    return None


def _date_seconds(value: Any) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((parsed - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def _remaining(item: Any) -> int | None:
    """Return the documented lock endDate countdown in seconds."""
    if not isinstance(item, dict):
        return None
    return _date_seconds(item.get("endDate"))


def _format_duration(seconds: Any) -> str | None:
    """Format seconds as DDd HH:MM:SS."""
    value = _number(seconds)
    if value is None:
        return None
    value = max(0, value)
    days, value = divmod(value, 86400)
    hours, value = divmod(value, 3600)
    minutes, seconds = divmod(value, 60)
    return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"


def _permissions(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    value = item.get("permissions")
    return value if isinstance(value, dict) else {}


def _attributes(lock: dict[str, Any], role: str | None = None, lock_type: str = "lock") -> dict[str, Any]:
    p = _permissions(lock)
    return {
        "lock_id": _id(lock), "role": role, "lock_type": lock_type, "status": lock.get("status"), "type": lock.get("type"),
        "remaining_seconds": _remaining(lock), "permissions": p,
        "can_add_time": p.get("add_time", p.get("addTime")), "can_remove_time": p.get("remove_time", p.get("removeTime")),
        "can_freeze": p.get("freeze", p.get("freeze_timer")), "can_unfreeze": p.get("unfreeze", p.get("unfreeze_timer")),
        "can_change_minimum_date": p.get("change_minimum_date"), "can_change_maximum_date": p.get("change_maximum_date"),
        "can_manage_extensions": p.get("manage_extensions"), "can_edit_safety": p.get("edit_bondage_safety_settings"),
        "wearer": lock.get("wearer"), "keyholder": lock.get("keyholder"),
        "start_date": lock.get("startDate"), "end_date": lock.get("endDate"),
        "minimum_date": lock.get("minLimitDate"), "maximum_date": lock.get("maxLimitDate"),
        "frozen": lock.get("frozen"), "timer_visible": lock.get("displayRemainingTime"),
        "history_time_visible": lock.get("timeLogsVisibility"), "extensions": lock.get("extensions"),
    }


def _keyholder_items(coordinator: ChasterCoordinator) -> list[dict[str, Any]]:
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    keyholder = data.get("keyholder")
    if not isinstance(keyholder, dict):
        return []
    value = keyholder.get("items") or keyholder.get("locks") or keyholder.get("results") or keyholder.get("data") or []
    if isinstance(value, dict):
        value = list(value.values())
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _username(value: Any) -> str | None:
    """Read a username from the Chaster user object, including nested API shapes."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if not isinstance(value, dict):
        return None

    candidate = value.get("username")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()

    for key in ("user", "profile", "account", "wearer", "keyholder"):
        nested = value.get(key)
        if nested is not value:
            result = _username(nested)
            if result:
                return result
    return None


def _nested_lock(item: dict[str, Any]) -> dict[str, Any]:
    nested = item.get("lock")
    return nested if isinstance(nested, dict) else item


def _active_lock(coordinator: ChasterCoordinator, role: str) -> dict[str, Any]:
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    if role == "wearer":
        locks = coordinator._dict_list(data.get("locks"))
    else:
        locks = []
        for item in _keyholder_items(coordinator):
            nested = item.get("lock") if isinstance(item.get("lock"), dict) else None
            locks.append({**item, **nested} if nested else item)
    active = [
        x
        for x in locks
        if isinstance(x, dict)
        and _id(x)
        and coordinator.is_active(x)
    ]
    return max(active, key=lambda x: str(x.get("startDate") or ""), default={})


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: ChasterCoordinator = hass.data[entry.domain][entry.entry_id]

    # Remove stale Keyholder lock entities created by older versions.
    # These may appear under either the My lock or Keyholder device.
    registry = er.async_get(hass)
    stale_prefix = f"{entry.entry_id}_lock_keyholder_"
    for entity in list(registry.entities.values()):
        if entity.config_entry_id != entry.entry_id:
            continue
        original_name = entity.original_name or ""
        registry_name = entity.name or ""
        if (
            entity.unique_id.startswith(stale_prefix)
            or original_name.startswith("Keyholder lock")
            or registry_name.startswith("Keyholder lock")
        ):
            registry.async_remove(entity.entity_id)

    entities = [
        ChasterUsernameSensor(coordinator, "wearer"),
        ChasterKeyholderUsernameSensor(coordinator),
        ChasterLockTitleSensor(coordinator, "wearer"),
        ChasterTimeLockedSensor(coordinator, "wearer"),
        ChasterTimeRemainingSensor(coordinator, "wearer"),
        ChasterHistorySensor(coordinator, "wearer"),
        ChasterUsernameSensor(coordinator, "keyholder"),
        ChasterWearerUsernameSensor(coordinator),
        ChasterLockTitleSensor(coordinator, "keyholder"),
        ChasterTimeLockedSensor(coordinator, "keyholder"),
        ChasterTimeRemainingSensor(coordinator, "keyholder"),
        ChasterHistorySensor(coordinator, "keyholder"),
    ]
    async_add_entities(entities)

    added_lock_ids: set[tuple[str, str]] = set()

    def add_dynamic_entities() -> None:
        data = coordinator.data if isinstance(coordinator.data, dict) else {}
        dynamic = []

        wearer_locks = coordinator._dict_list(data.get("locks"))
        shared_locks = coordinator._dict_list(data.get("shared_locks"))

        # Only create wearer lock sensors. Keyholder lock sensors are omitted.
        for item in wearer_locks:
            lock_id = _id(item)
            if not lock_id:
                continue
            for device_role in ("wearer", "keyholder"):
                key = (device_role, f"wearer:{lock_id}")
                if key not in added_lock_ids:
                    added_lock_ids.add(key)
                    dynamic.append(
                        ChasterLockSensor(
                            coordinator,
                            item,
                            device_role,
                            source_role="wearer",
                        )
                    )

        # Shared locks are mirrored onto both device views.
        for item in shared_locks:
            lock_id = _id(item)
            if not lock_id:
                continue
            for device_role in ("wearer", "keyholder"):
                key = (device_role, f"shared:{lock_id}")
                if key not in added_lock_ids:
                    added_lock_ids.add(key)
                    dynamic.append(
                        ChasterSharedLockSensor(
                            coordinator,
                            item,
                            device_role,
                        )
                    )

        if dynamic:
            async_add_entities(dynamic)

    add_dynamic_entities()

    def _handle_coordinator_update() -> None:
        add_dynamic_entities()

    remove_listener = coordinator.async_add_listener(_handle_coordinator_update)
    entry.async_on_unload(remove_listener)


class ChasterUsernameSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:account"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        suffix = "wearer_username" if role == "wearer" else "keyholder_username_v2"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_name = "Wearer Username" if role == "wearer" else "Keyholder Username"

    @property
    def native_value(self):
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        return _username(data.get("profile"))


class ChasterWearerUsernameSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:account"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator):
        super().__init__(coordinator, "keyholder")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_keyholder_device_wearer_username"
        self._attr_name = "Wearer Username"

    @property
    def native_value(self):
        lock = _active_lock(self.coordinator, "keyholder")
        if not lock:
            return None
        for key in ("wearer", "user", "profile", "account"):
            username = _username(lock.get(key))
            if username:
                return username
        for key in ("wearerUsername", "wearer_username"):
            username = _username(lock.get(key))
            if username:
                return username
        return None


class ChasterKeyholderUsernameSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:account-key"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator):
        super().__init__(coordinator, "wearer")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_my_lock_keyholder_username"
        self._attr_name = "Keyholder Username"

    @property
    def native_value(self):
        lock = _active_lock(self.coordinator, "wearer")
        return _username(lock.get("keyholder")) if lock else None


class ChasterTimeLockedSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:timer-lock"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        suffix = "my_lock_time_locked" if role == "wearer" else "keyholder_time_locked"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_name = "Time Locked"

    @property
    def native_value(self):
        lock = _active_lock(self.coordinator, self.role)
        if not lock:
            return None
        start = lock.get("startDate")
        if not isinstance(start, str):
            return None
        try:
            parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return None


class ChasterTimeRemainingSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:timer-sand"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        suffix = "my_lock_time_remaining" if role == "wearer" else "keyholder_time_remaining"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_name = "Time Remaining"

    @property
    def native_value(self):
        lock = _active_lock(self.coordinator, self.role)
        return _format_duration(_remaining(lock)) if lock else None


class ChasterLockTitleSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:format-title"

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{role}_lock_title"
        self._attr_name = "Lock Title"

    @property
    def _lock(self):
        return _active_lock(self.coordinator, self.role)

    @property
    def native_value(self):
        lock = self._lock
        return lock.get("title") if lock else None

    @property
    def extra_state_attributes(self):
        lock = self._lock
        return {"lock_id": _id(lock), "role": self.role, "status": lock.get("status")} if lock else {"lock_id": None, "role": "none"}


class ChasterHistorySensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:history"

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{role}_history_sensor"
        self._attr_name = "Current lock history"

    @property
    def native_value(self):
        history = self.coordinator.data.get("history_by_role", {}).get(self.role, [])
        return len(history) if isinstance(history, list) else len(self.coordinator._dict_list(history))

    @property
    def extra_state_attributes(self):
        history = self.coordinator.data.get("history_by_role", {}).get(self.role, [])
        if not isinstance(history, list):
            history = self.coordinator._dict_list(history)
        lock = _active_lock(self.coordinator, self.role)
        role = self.role if _id(lock) else "none"
        return {"lock_id": _id(lock), "role": role, "lock_type": "history", "entries": history[-50:]}


class ChasterLockSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:lock-clock"

    def __init__(self, coordinator, initial, role, source_role=None):
        super().__init__(coordinator, role)
        self.lock_id = _id(initial)
        self.role = role
        self.source_role = source_role or role
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_lock_{self.source_role}_"
            f"{self.lock_id}_{role}"
        )
        source_name = "My lock" if self.source_role == "wearer" else "Keyholder lock"
        self._attr_name = f"{source_name} - {_name(initial)}"

    @property
    def _lock(self):
        if self.source_role == "wearer":
            return next(
                (x for x in self.coordinator._dict_list(self.coordinator.data.get("locks"))
                 if _id(x) == self.lock_id),
                {},
            )
        for item in _keyholder_items(self.coordinator):
            lock = _nested_lock(item)
            if _id(lock) == self.lock_id:
                return lock
        return {}

    @property
    def native_value(self):
        return _format_duration(_remaining(self._lock)) if self._lock else None

    @property
    def extra_state_attributes(self):
        return _attributes(self._lock, self.role, "active_lock")


class ChasterSharedLockSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:account-multiple-lock"

    def __init__(self, coordinator, initial, role="keyholder"):
        super().__init__(coordinator, role)
        self.shared_id = _id(initial)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_shared_{self.shared_id}_{role}"
        self._attr_name = f"Shared lock - {_name(initial)}"

    @property
    def _lock(self):
        return next((x for x in self.coordinator.data.get("shared_locks", []) if _id(x) == self.shared_id), {})

    @property
    def native_value(self):
        lock = self._lock
        return lock.get("status", "unknown") if lock else "unknown"

    @property
    def extra_state_attributes(self):
        lock = self._lock
        return {"lock_type": "shared", "role": "owner", "shared_lock_id": self.shared_id, **{k: v for k, v in lock.items() if k not in ("token", "accessToken", "secret")}}
