from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval

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
    """Format seconds as HH:MM:SS."""
    value = _number(seconds)
    if value is None:
        return None
    value = max(0, value)
    days, value = divmod(value, 86400)
    hours, value = divmod(value, 3600)
    minutes, seconds = divmod(value, 60)
    total_hours = days * 24 + hours
    return f"{total_hours:02d}:{minutes:02d}:{seconds:02d}"


def _lock_type(lock: Any) -> str | None:
    """Read the lock type across the API's possible response shapes."""
    if not isinstance(lock, dict):
        return None
    for key in ("type", "lockType", "lock_type", "mode"):
        value = lock.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for nested_key in ("value", "type", "name", "slug", "id"):
                nested = value.get(nested_key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return None


def _permissions(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    value = item.get("permissions")
    return value if isinstance(value, dict) else {}


def _attributes(lock: dict[str, Any], role: str | None = None, lock_type: str = "lock") -> dict[str, Any]:
    p = _permissions(lock)
    return {
        "lock_id": _id(lock), "role": role, "lock_type": lock_type, "status": lock.get("status"), "type": lock.get("type"),
        "remaining_seconds": _remaining(lock),
        "remaining": _format_duration(_remaining(lock)), "permissions": p,
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


def _task_entries(history: Any) -> list[dict[str, Any]]:
    """Return Tasks extension action entries from lock history."""
    entries = history if isinstance(history, list) else []
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        action = str(
            entry.get("type")
            or entry.get("action")
            or entry.get("actionType")
            or entry.get("event")
            or ""
        ).strip().lower().replace("-", "_").replace(" ", "_")
        if "task" in action and (
            "assigned" in action or "completed" in action or "failed" in action
        ):
            result.append(entry)
    return result


def _task_points_from_entry(entry: dict[str, Any]) -> int | None:
    """Read a task's point value from common action-log shapes."""
    for container in (
        entry,
        entry.get("task"),
        entry.get("payload"),
        entry.get("data"),
        entry.get("details"),
    ):
        if not isinstance(container, dict):
            continue
        for key in ("points", "taskPoints", "task_points", "pointsAwarded", "points_awarded"):
            value = _number(container.get(key))
            if value is not None:
                return value
    return None


def _task_points_earned(history: Any) -> int:
    total = 0
    for entry in _task_entries(history):
        action = str(
            entry.get("type")
            or entry.get("action")
            or entry.get("actionType")
            or entry.get("event")
            or ""
        ).strip().lower().replace("-", "_").replace(" ", "_")
        if "completed" in action:
            points = _task_points_from_entry(entry)
            if points is not None:
                total += points
    return total


def _find_task_points_required(value: Any) -> int | None:
    """Find the Tasks extension's configured point target without using task value."""
    keys = {
        "requiredpoints",
        "pointsrequired",
        "targetpoints",
        "pointstarget",
        "unlockpoints",
        "pointstounlock",
        "required_points",
        "points_required",
        "target_points",
        "points_target",
        "unlock_points",
        "points_to_unlock",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).replace("-", "_").replace(" ", "_").lower()
            compact = normalized.replace("_", "")
            if normalized in keys or compact in keys:
                number = _number(item)
                if number is not None:
                    return number
            result = _find_task_points_required(item)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in value:
            result = _find_task_points_required(item)
            if result is not None:
                return result
    return None


def _task_points(coordinator: ChasterCoordinator, role: str) -> tuple[int | None, int | None]:
    """Return (required, remaining) task points for the active lock."""
    lock = _active_lock(coordinator, role)
    if not lock:
        return None, None

    required = _find_task_points_required(lock)
    history = coordinator.data.get("history_by_role", {}).get(role, [])
    if required is None:
        required = _find_task_points_required(history)

    if required is None:
        return 0, 0

    earned = _task_points_earned(history)
    return required, max(0, required - earned)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: ChasterCoordinator = hass.data[entry.domain][entry.entry_id]

    # Remove sensor entities that are not part of the requested list.
    registry = er.async_get(hass)
    allowed = {
        "Wearer Username", "Keyholder Username", "Lock Title", "Lock Type",
        "Start Date", "End Date", "Timer Visible", "Time Locked",
        "Time Remaining", "Session Role", "Task Points",
        "Task Points Required", "Task Points Remaining",
    }
    for entity in list(registry.entities.values()):
        if entity.config_entry_id == entry.entry_id and entity.domain == "sensor":
            if (entity.original_name or entity.name or "") not in allowed:
                registry.async_remove(entity.entity_id)

    # Remove stale Keyholder lock entities created by older versions.
    # These may appear under either the My lock or Keyholder device.
    registry = er.async_get(hass)
    stale_entity_ids = {
        "sensor.chas_chaster_my_lock_my_lock_keyholder_lock",
        "sensor.chas_chaster_keyholder_my_lock_keyholder_lock",
        "sensor.chaster_my_lock_my_lock_keyholder_lock",
    }
    for entity_id in stale_entity_ids:
        if entity_id in registry.entities:
            registry.async_remove(entity_id)
    stale_prefix = f"{entry.entry_id}_lock_keyholder_"
    for entity in list(registry.entities.values()):
        if entity.config_entry_id != entry.entry_id:
            continue
        original_name = entity.original_name or ""
        registry_name = entity.name or ""
        legacy_my_lock_keyholder = (
            entity.unique_id.startswith(f"{entry.entry_id}_lock_wearer_")
            and entity.unique_id.endswith("_keyholder")
        )
        stale_history_sensor = (
            entity.unique_id.endswith("_history_sensor")
            or original_name == "Current lock history"
            or registry_name == "Current lock history"
        )
        stale_dynamic_sensor = (
            "_lock_" in entity.unique_id
            or entity.unique_id.startswith(f"{entry.entry_id}_shared_")
            or original_name.startswith("My lock -")
            or registry_name.startswith("My lock -")
            or original_name.startswith("Shared lock -")
            or registry_name.startswith("Shared lock -")
        )
        if (
            entity.unique_id.startswith(stale_prefix)
            or legacy_my_lock_keyholder
            or stale_dynamic_sensor
            or original_name.startswith("Keyholder lock")
            or registry_name.startswith("Keyholder lock")
            or stale_history_sensor
        ):
            registry.async_remove(entity.entity_id)

    entities = [
        ChasterUsernameSensor(coordinator, "wearer"),
        ChasterKeyholderUsernameSensor(coordinator),
        ChasterLockTitleSensor(coordinator, "wearer"),
        ChasterLockTypeSensor(coordinator, "wearer"),
        ChasterStartDateSensor(coordinator, "wearer"),
        ChasterEndDateSensor(coordinator, "wearer"),
        ChasterTimerVisibleSensor(coordinator, "wearer"),
        ChasterTimeLockedSensor(coordinator, "wearer"),
        ChasterTimeRemainingSensor(coordinator, "wearer"),
        ChasterSessionRoleSensor(coordinator, "wearer"),
        ChasterTaskPointsSensor(coordinator, "wearer"),
        ChasterTaskPointsRequiredSensor(coordinator, "wearer"),
        ChasterTaskPointsRemainingSensor(coordinator, "wearer"),
        ChasterUsernameSensor(coordinator, "keyholder"),
        ChasterWearerUsernameSensor(coordinator),
        ChasterLockTitleSensor(coordinator, "keyholder"),
        ChasterLockTypeSensor(coordinator, "keyholder"),
        ChasterStartDateSensor(coordinator, "keyholder"),
        ChasterEndDateSensor(coordinator, "keyholder"),
        ChasterTimerVisibleSensor(coordinator, "keyholder"),
        ChasterTimeLockedSensor(coordinator, "keyholder"),
        ChasterTimeRemainingSensor(coordinator, "keyholder"),
        ChasterSessionRoleSensor(coordinator, "keyholder"),
        ChasterTaskPointsSensor(coordinator, "keyholder"),
        ChasterTaskPointsRequiredSensor(coordinator, "keyholder"),
        ChasterTaskPointsRemainingSensor(coordinator, "keyholder"),
    ]
    async_add_entities(entities)


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


class _ChasterCountdownSensor(ChasterEntity, SensorEntity):
    """Refresh countdown sensor state locally every second."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._countdown_unsub = async_track_time_interval(
            self.hass,
            self._async_update_countdown,
            timedelta(seconds=1),
        )

    async def async_will_remove_from_hass(self) -> None:
        if hasattr(self, "_countdown_unsub"):
            self._countdown_unsub()
        await super().async_will_remove_from_hass()

    @callback
    def _async_update_countdown(self, _now) -> None:
        self.async_write_ha_state()


class ChasterTimeLockedSensor(_ChasterCountdownSensor):
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
            elapsed = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
            return _format_duration(elapsed)
        except (TypeError, ValueError, OverflowError):
            return None


class ChasterTimeRemainingSensor(_ChasterCountdownSensor):
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


class ChasterSessionRoleSensor(ChasterEntity, SensorEntity):
    """Expose the current session role, matching Chastify."""

    _attr_icon = "mdi:account-switch"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        suffix = "my_lock_session_role" if role == "wearer" else "keyholder_session_role"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_name = "Session Role"

    @property
    def native_value(self):
        return self.role


class ChasterTaskPointsSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:star-circle"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        suffix = "my_lock_task_points" if role == "wearer" else "keyholder_task_points"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_name = "Task Points"

    @property
    def native_value(self):
        history = self.coordinator.data.get("history_by_role", {}).get(self.role, [])
        return _task_points_earned(history)


class ChasterTaskPointsRequiredSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:target"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        suffix = "my_lock_task_points_required" if role == "wearer" else "keyholder_task_points_required"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_name = "Task Points Required"

    @property
    def native_value(self):
        required, _ = _task_points(self.coordinator, self.role)
        return 0 if required is None else required


class ChasterTaskPointsRemainingSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:counter"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        suffix = "my_lock_task_points_remaining" if role == "wearer" else "keyholder_task_points_remaining"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"
        self._attr_name = "Task Points Remaining"

    @property
    def native_value(self):
        _, remaining = _task_points(self.coordinator, self.role)
        return 0 if remaining is None else remaining


class _ChasterLockFieldSensor(ChasterEntity, SensorEntity):
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role, suffix, name, field_name, icon="mdi:lock"):
        super().__init__(coordinator, role)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{role}_{suffix}"
        self._attr_name = name
        self._field_name = field_name
        self._attr_icon = icon

    @property
    def native_value(self):
        lock = _active_lock(self.coordinator, self.role)
        if not lock:
            return None
        return lock.get(self._field_name)


class ChasterLockTypeSensor(ChasterEntity, SensorEntity):
    _attr_icon = "mdi:lock"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, role):
        super().__init__(coordinator, role)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{role}_lock_type"
        self._attr_name = "Lock Type"

    @property
    def native_value(self):
        return _lock_type(_active_lock(self.coordinator, self.role))


class ChasterStartDateSensor(_ChasterLockFieldSensor):
    def __init__(self, coordinator, role):
        super().__init__(coordinator, role, "start_date", "Start Date", "startDate", "mdi:calendar-start")


class ChasterEndDateSensor(_ChasterLockFieldSensor):
    def __init__(self, coordinator, role):
        super().__init__(coordinator, role, "end_date", "End Date", "endDate", "mdi:calendar-end")


class ChasterTimerVisibleSensor(_ChasterLockFieldSensor):
    def __init__(self, coordinator, role):
        super().__init__(coordinator, role, "timer_visible", "Timer Visible", "displayRemainingTime", "mdi:timer-outline")


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
