"""Role-specific calendars for Chaster lock sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .coordinator import ChasterCoordinator
from .entity import ChasterEntity


def _parse_datetime(value: Any) -> datetime | None:
    """Parse Chaster ISO timestamps and Unix timestamps into aware datetimes."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            timestamp = float(value)
            if abs(timestamp) >= 10_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _first_datetime(lock: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    """Find a lock date in direct fields or a nested timer/date payload."""
    for source in (lock, lock.get("timer"), lock.get("timing"), lock.get("dates")):
        if not isinstance(source, dict):
            continue
        for key in keys:
            parsed = _parse_datetime(source.get(key))
            if parsed is not None:
                return parsed
    return None


def _first_number(lock: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    """Find a numeric timer value in the lock or its nested timing payloads."""
    for source in (lock, lock.get("timer"), lock.get("timing")):
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            # NaN, infinities, and integers too large to convert to float
            # are invalid timer durations. Reject them before timedelta math.
            try:
                number = float(value)
            except (OverflowError, ValueError):
                continue
            if math.isfinite(number) and number >= 0:
                return number
    return None


def _keyholder_items(coordinator: ChasterCoordinator) -> list[dict[str, Any]]:
    """Return keyholder lock records, unwrapping API collection shapes."""
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    keyholder = data.get("keyholder")
    if not isinstance(keyholder, dict):
        return []
    items: Any = (
        keyholder.get("items")
        or keyholder.get("locks")
        or keyholder.get("results")
        or keyholder.get("data")
        or []
    )
    if isinstance(items, dict):
        items = list(items.values())
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _lock_for_item(item: dict[str, Any]) -> dict[str, Any]:
    """Flatten a keyholder association containing a nested lock object."""
    nested = item.get("lock")
    return {**item, **nested} if isinstance(nested, dict) else item


def _role_locks(coordinator: ChasterCoordinator, role: str) -> list[dict[str, Any]]:
    """Return locks for one role without mixing wearer and keyholder sessions."""
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    if role == "keyholder":
        source = [_lock_for_item(item) for item in _keyholder_items(coordinator)]
    else:
        source = coordinator._dict_list(data.get("locks"))

    locks_by_id: dict[str, dict[str, Any]] = {}
    for lock in source:
        lock_id = coordinator.lock_id(lock)
        if lock_id:
            locks_by_id[lock_id] = lock

    # Some API responses omit the active wearer lock from /locks. Include the
    # separately fetched current lock only when it is not known to be a
    # keyholder lock, so it cannot leak into the My lock calendar by mistake.
    if role == "wearer":
        current_lock = data.get("current_lock")
        if not isinstance(current_lock, dict):
            current_lock = coordinator.current_lock
        current_id = coordinator.lock_id(current_lock)
        keyholder_ids = {
            coordinator.lock_id(_lock_for_item(item))
            for item in _keyholder_items(coordinator)
        }
        if current_id and current_id not in keyholder_ids and current_id not in locks_by_id:
            locks_by_id[current_id] = current_lock

    return list(locks_by_id.values())


class ChasterSessionCalendar(ChasterEntity, CalendarEntity):
    """Expose one Chaster role's lock sessions as calendar events."""

    _attr_icon = "mdi:calendar-lock"

    def __init__(self, coordinator: ChasterCoordinator, role: str) -> None:
        super().__init__(coordinator, role)
        self.role = role
        self._attr_name = None
        suffix = "sessions_calendar" if role == "wearer" else "sessions_calendar_keyholder"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{suffix}"

    def _events(self) -> list[CalendarEvent]:
        events_by_id: dict[str, CalendarEvent] = {}
        for lock in _role_locks(self.coordinator, self.role):
            lock_id = self.coordinator.lock_id(lock)
            if not lock_id:
                continue
            start = _first_datetime(lock, ("startDate", "startAt", "startedAt", "createdAt"))
            # Prefer a live remaining-time snapshot when available, anchored to
            # the coordinator refresh so repeated calendar reads do not drift.
            end = _first_datetime(
                lock, ("endDate", "endAt", "unlockDate", "unlockAt", "maxLimitDate")
            )
            remaining = _first_number(
                lock, ("timeRemainingSeconds", "remainingSeconds", "remainingTimeSeconds")
            )
            updated_at = getattr(self.coordinator, "last_update_success_time", None)
            if isinstance(updated_at, datetime):
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                else:
                    updated_at = updated_at.astimezone(timezone.utc)
                if remaining is not None:
                    try:
                        end = updated_at + timedelta(seconds=remaining)
                    except (OverflowError, ValueError):
                        # An implausibly large API value must not break the
                        # whole calendar entity; retain the absolute end date.
                        pass

            # Reaching the expected unlock time does not necessarily mean the
            # lock ended. Active state is authoritative. Keep an overdue active
            # session visible even when this HA version/coordinator has no
            # last_update_success_time (or the live timer is unavailable).
            now = datetime.now(timezone.utc)
            if end is not None and end <= now and self.coordinator.is_active(lock):
                interval = getattr(self.coordinator, "update_interval", None)
                extension = interval.total_seconds() if isinstance(interval, timedelta) else 60
                end = now + timedelta(seconds=max(60, extension))

            # Keep the explicit absolute end as fallback when live timing is
            # unavailable or hidden; never fabricate an end date.
            if start is None or end is None or end <= start:
                continue

            is_active = self.coordinator.is_active(lock)
            if is_active:
                local_start = dt_util.as_local(start)
                title = f"Chaster — Active session — started {local_start:%H:%M}"
            else:
                title = str(
                    lock.get("customWearerName")
                    or lock.get("title")
                    or lock.get("name")
                    or f"Chaster session {lock_id}"
                )
            status = lock.get("status") or lock.get("state") or "unknown"
            role_label = "My lock" if self.role == "wearer" else "Keyholder lock"
            events_by_id[lock_id] = CalendarEvent(
                summary=title,
                start=start,
                end=end,
                description=f"{role_label} session\nStatus: {status}\nLock ID: {lock_id}",
                uid=f"chaster-{self.role}-{lock_id}",
            )

        return sorted(events_by_id.values(), key=lambda event: event.start)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next ongoing or upcoming session for this role."""
        now = datetime.now(timezone.utc)
        return next((event for event in self._events() if event.end > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return role-specific sessions overlapping the requested calendar range."""
        return [
            event
            for event in self._events()
            if event.start < end_date and event.end > start_date
        ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up separate My lock and Keyholder calendars."""
    coordinator: ChasterCoordinator = hass.data[entry.domain][entry.entry_id]
    async_add_entities(
        [
            ChasterSessionCalendar(coordinator, "wearer"),
            ChasterSessionCalendar(coordinator, "keyholder"),
        ]
    )
