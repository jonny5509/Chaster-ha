from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers import entity_registry as er

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


class ChasterReadyToUnlockBinary(_CurrentLockBinary):
    def __init__(self, coordinator, role):
        super().__init__(
            coordinator,
            role,
            "ready_to_unlock",
            "Ready to unlock",
            "mdi:lock-open-outline",
        )

    @staticmethod
    def _timer_expired(lock: dict) -> bool:
        for key in ("endDate", "endAt", "unlockDate", "unlockAt"):
            value = lock.get(key)
            if not value:
                continue
            if isinstance(value, (int, float)):
                timestamp = float(value) / 1000 if float(value) > 10000000000 else float(value)
                return datetime.now(timezone.utc).timestamp() >= timestamp
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return datetime.now(timezone.utc) >= parsed
                except ValueError:
                    continue
        return False

    @property
    def is_on(self):
        lock = self._lock
        if not lock or not self.coordinator.is_active(lock):
            return False
        status = str(lock.get("status", lock.get("state", ""))).strip().lower().replace("_", "-").replace(" ", "-")
        return self._timer_expired(lock) and status in {
            "locked",
            "locking",
            "running",
            "active",
            "started",
            "start",
            "frozen",
            "paused",
            "in-progress",
            "inprogress",
            "ready-to-unlock",
            "readyforunlock",
        }

    @property
    def extra_state_attributes(self):
        lock = self._lock
        return {
            "lock_id": self.coordinator.lock_id(lock),
            "role": self.role,
            "status": lock.get("status") if lock else None,
            "end_date": next(
                (lock.get(key) for key in ("endDate", "endAt", "unlockDate", "unlockAt") if lock.get(key)),
                None,
            ) if lock else None,
        }


class ChasterFrozenBinary(_CurrentLockBinary):
    def __init__(self, coordinator, role):
        super().__init__(coordinator, role, "frozen", "Frozen", "mdi:snowflake")

    @property
    def is_on(self):
        lock = self._lock
        return bool(lock.get("frozen", lock.get("isFrozen", False)))


def _active_role_lock(coordinator, role: str) -> dict:
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    if role == "wearer":
        locks = coordinator._dict_list(data.get("locks"))
    else:
        keyholder = data.get("keyholder", {})
        items = (
            keyholder.get("items")
            or keyholder.get("locks")
            or keyholder.get("results")
            or keyholder.get("data")
            or []
        ) if isinstance(keyholder, dict) else []
        if isinstance(items, dict):
            items = list(items.values())
        locks = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                lock = item.get("lock") if isinstance(item.get("lock"), dict) else item
                if isinstance(lock, dict):
                    locks.append(lock)
    active = [
        lock for lock in locks
        if isinstance(lock, dict)
        and coordinator.lock_id(lock)
        and coordinator.is_active(lock)
    ]
    return max(
        active,
        key=lambda x: str(x.get("startDate") or x.get("startAt") or x.get("createdAt") or ""),
        default={},
    )


def _task_action_state(history) -> tuple[bool, dict]:
    """Return whether the latest Tasks action leaves a task assigned."""
    entries = history if isinstance(history, list) else []
    task_entries = []
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
        if action in {
            "tasks_task_assigned",
            "tasks_task_completed",
            "tasks_task_failed",
        } or ("task" in action and ("assigned" in action or "completed" in action or "failed" in action)):
            task_entries.append((entry, action))

    if not task_entries:
        return False, {}

    entry, action = task_entries[-1]
    return action.endswith("assigned"), entry


class ChasterTaskAssignedBinary(_CurrentLockBinary):
    def __init__(self, coordinator, role):
        super().__init__(
            coordinator,
            role,
            "task_assigned",
            "Task Assigned",
            "mdi:clipboard-check-outline",
        )

    @property
    def is_on(self):
        lock = _active_role_lock(self.coordinator, self.role)
        if not lock:
            return False
        history = self.coordinator.data.get("history_by_role", {}).get(self.role, [])
        assigned, _ = _task_action_state(history)
        return assigned

    @property
    def extra_state_attributes(self):
        lock = _active_role_lock(self.coordinator, self.role)
        history = self.coordinator.data.get("history_by_role", {}).get(self.role, [])
        assigned, entry = _task_action_state(history)
        return {
            "lock_id": self.coordinator.lock_id(lock),
            "role": self.role,
            "assigned": assigned,
            "task_action": (
                entry.get("type")
                or entry.get("action")
                or entry.get("actionType")
                or entry.get("event")
            ) if entry else None,
            "task": entry.get("task") if isinstance(entry, dict) else None,
        }


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: ChasterCoordinator = hass.data[entry.domain][entry.entry_id]

    registry = er.async_get(hass)
    allowed = {"Locked", "Ready to unlock", "Frozen", "Task Assigned"}
    for entity in list(registry.entities.values()):
        if entity.config_entry_id == entry.entry_id and entity.domain == "binary_sensor":
            if (entity.original_name or entity.name or "") not in allowed:
                registry.async_remove(entity.entity_id)

    for entity in list(registry.entities.values()):
        if entity.config_entry_id != entry.entry_id:
            continue
        unique_id = (entity.unique_id or "").lower()
        original_name = (entity.original_name or "").lower()
        name = (entity.name or "").lower()
        if (
            unique_id.endswith("_obedience_connected")
            or "obedience connected" in original_name
            or "obedience connected" in name
            or "obedience_connected" in unique_id
        ):
            registry.async_remove(entity.entity_id)

    entities = []
    for role in ("wearer", "keyholder"):
        entities.extend([
            ChasterLockedBinary(coordinator, role),
            ChasterReadyToUnlockBinary(coordinator, role),
            ChasterFrozenBinary(coordinator, role),
            ChasterTaskAssignedBinary(coordinator, role),
        ])
    async_add_entities(entities)
