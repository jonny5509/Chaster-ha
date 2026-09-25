from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import entity_registry as er

from .api import ChasterApiError
from .coordinator import ChasterCoordinator
from .entity import ChasterEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: ChasterCoordinator = hass.data[entry.domain][entry.entry_id]

    # Remove the old Keyholder - Archive entity from the registry so it
    # does not remain visible after the button is no longer created.
    registry = er.async_get(hass)
    registry.async_remove(f"{entry.entry_id}_keyholder_archive")

    entities = []
    for role, label in (("wearer", "My lock"), ("keyholder", "Keyholder")):
        entities.append(
            ChasterActionButton(
                coordinator,
                "refresh",
                "Refresh Chaster",
                "mdi:refresh",
                role,
            )
        )
        if role == "wearer":
            # Freeze/unfreeze are not exposed on the "My lock" device.
            actions = (
                ("history", "Refresh history", "mdi:history"),
                ("unlock", "Unlock", "mdi:lock-open"),
                ("emergency_unlock", "Emergency unlock", "mdi:alert-octagon"),
                ("archive", "Archive", "mdi:archive"),
            )
        else:
            actions = (
                ("history", "Refresh history", "mdi:history"),
                ("freeze", "Freeze", "mdi:snowflake"),
                ("unfreeze", "Unfreeze", "mdi:snowflake-off"),
                ("unlock", "Unlock", "mdi:lock-open"),
            )
        for action, suffix, icon in actions:
            entities.append(ChasterActionButton(coordinator, action, f"{label} - {suffix}", icon, role))
    async_add_entities(entities)


class ChasterActionButton(ChasterEntity, ButtonEntity):
    _attr_entity_category = None

    def __init__(self, coordinator, action: str, name: str, icon: str, role: str | None) -> None:
        super().__init__(coordinator, role)
        self._action = action
        self._role = role
        self._attr_name = name
        self._attr_icon = icon
        role_id = role or "general"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{role_id}_{action}"

    @staticmethod
    def _status(lock: dict[str, Any] | None) -> str:
        if not isinstance(lock, dict):
            return ""
        return str(lock.get("status", lock.get("state", ""))).strip().lower().replace("_", "-").replace(" ", "-")

    @staticmethod
    def _terminal(lock: dict[str, Any]) -> bool:
        return ChasterActionButton._status(lock) in {
            "unlocked", "archived", "deserted", "ended", "completed", "cancelled", "canceled",
        }

    def _wearer_locks(self) -> list[dict[str, Any]]:
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        value = data.get("locks", [])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for key in ("items", "results", "data", "locks", "sessions", "entries"):
                items = value.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
                if isinstance(items, dict):
                    return [item for item in items.values() if isinstance(item, dict)]
        return []

    def _keyholder_locks(self) -> list[dict[str, Any]]:
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        keyholder = data.get("keyholder")
        if not isinstance(keyholder, dict):
            return []
        value = keyholder.get("items") or keyholder.get("locks") or keyholder.get("results") or keyholder.get("data") or []
        if isinstance(value, dict):
            value = list(value.values())
        result = []
        for item in value if isinstance(value, list) else []:
            if not isinstance(item, dict):
                continue
            nested = item.get("lock") if isinstance(item.get("lock"), dict) else None
            if nested is not None:
                # Keep wrapper fields too; Chaster responses can expose freeze
                # state alongside the nested lock object.
                lock = {**item, **nested}
            else:
                lock = item
            if isinstance(lock, dict):
                result.append(lock)
        return result

    def _candidate_locks(self) -> list[dict[str, Any]]:
        if self._role == "wearer":
            locks = self._wearer_locks()
        elif self._role == "keyholder":
            locks = self._keyholder_locks()
        else:
            locks = []
        candidates = []
        for lock in locks:
            if not self.coordinator.lock_id(lock):
                continue
            if self._terminal(lock) and not (self._action == "archive" and self._status(lock) == "unlocked"):
                continue
            candidates.append(lock)
        return candidates

    def _lock_sort_key(self, lock: dict[str, Any]) -> str:
        return str(lock.get("startDate") or lock.get("startAt") or lock.get("createdAt") or "")

    @property
    def _lock(self) -> dict[str, Any] | None:
        candidates = self._candidate_locks()
        if self._action == "archive":
            return max(candidates, key=self._lock_sort_key, default=None)
        return max([lock for lock in candidates if self.coordinator.is_active(lock)], key=self._lock_sort_key, default=None)

    @staticmethod
    def _is_frozen(lock: dict[str, Any] | None) -> bool:
        if not isinstance(lock, dict):
            return False

        def truthy(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes", "on", "frozen"}
            return False

        for key in ("frozen", "isFrozen", "is_frozen", "freeze", "paused"):
            if truthy(lock.get(key)):
                return True

        for key in ("state", "status", "mode"):
            value = lock.get(key)
            if isinstance(value, str):
                normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
                if normalized in {
                    "frozen",
                    "paused",
                    "freeze",
                    "locked-frozen",
                    "locked-frozen-by-keyholder",
                }:
                    return True

        for key in ("lock", "session", "timer"):
            nested = lock.get(key)
            if isinstance(nested, dict) and ChasterActionButton._is_frozen(nested):
                return True

        return False

    def _mode_allows_action(self, lock: dict[str, Any] | None) -> bool:
        status = self._status(lock)
        if not status:
            return False
        if self._action == "freeze":
            return status in {"locked", "locking", "running", "active", "started", "start", "in-progress", "inprogress"}
        if self._action == "unfreeze":
            return self._is_frozen(lock)
        if self._action == "unlock":
            return status in {"locked", "locking", "running", "active", "started", "start", "frozen", "paused", "in-progress", "inprogress", "ready-to-unlock", "readyforunlock"}
        if self._action == "emergency_unlock":
            return self._role == "wearer" and status in {"locked", "locking", "running", "active", "started", "start", "frozen", "paused", "in-progress", "inprogress"}
        if self._action == "archive":
            return status in {"unlocked", "ready-to-archive"}
        if self._action == "history":
            return self.coordinator.is_active(lock)
        return True

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self._action == "refresh":
            return True
        if not self.coordinator.enable_lock_actions:
            return False
        lock = self._lock
        return bool(lock and self.coordinator.lock_id(lock) and self._mode_allows_action(lock))

    async def async_press(self) -> None:
        if self._action == "refresh":
            await self.coordinator.async_request_refresh()
            return
        if not self.coordinator.enable_lock_actions:
            return
        lock = self._lock
        lock_id = self.coordinator.lock_id(lock) if lock else None
        if not lock_id or not self._mode_allows_action(lock):
            await self.coordinator.async_request_refresh()
            return
        if self._action != "history":
            try:
                fresh = await self.coordinator.api.lock(lock_id)
            except ChasterApiError:
                await self.coordinator.async_request_refresh()
                return
            if not isinstance(fresh, dict) or self.coordinator.lock_id(fresh) != lock_id:
                await self.coordinator.async_request_refresh()
                return
            lock = fresh
            if not self._mode_allows_action(lock):
                await self.coordinator.async_request_refresh()
                return
        if self._action == "history":
            result = await self.coordinator.api.history(lock_id)
            self.hass.bus.async_fire("chaster_history", {"lock_id": lock_id, "role": self._role, "history": result})
        elif self._action == "freeze":
            await self.coordinator.api.freeze(lock_id, True)
        elif self._action == "unfreeze":
            await self.coordinator.api.freeze(lock_id, False)
        elif self._action == "unlock":
            await self.coordinator.api.unlock(lock_id)
        elif self._action == "emergency_unlock":
            if self._role != "wearer":
                await self.coordinator.async_request_refresh()
                return
            await self.coordinator.api.emergency_unlock(lock_id)
        elif self._action == "archive":
            await self.coordinator.api.archive(lock_id, keyholder=self._role == "keyholder")

            # Remove the archived lock from the coordinator immediately.
            # The coordinator normally preserves missing locks between API
            # refreshes, which would otherwise keep the Archive button
            # available until another fresh API result replaces the old data.
            data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
            if data:
                locks = data.get("locks")
                if isinstance(locks, list):
                    data["locks"] = [
                        item for item in locks
                        if self.coordinator.lock_id(item) != lock_id
                    ]

                current = data.get("current_lock")
                if (
                    isinstance(current, dict)
                    and self.coordinator.lock_id(current) == lock_id
                ):
                    data["current_lock"] = None

                keyholder = data.get("keyholder")
                if isinstance(keyholder, dict):
                    for key in ("items", "locks", "results", "data"):
                        items = keyholder.get(key)
                        if isinstance(items, list):
                            keyholder[key] = [
                                item for item in items
                                if self.coordinator.lock_id(item) != lock_id
                            ]

        await self.coordinator.async_request_refresh()
