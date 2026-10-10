"""Calendar platform for Chaster sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .coordinator import ChasterCoordinator
from .entity import ChasterEntity


def _parse_datetime(value: Any) -> datetime | None:
    """Parse Chaster ISO timestamps and Unix timestamps into aware datetimes."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
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
    for key in keys:
        parsed = _parse_datetime(lock.get(key))
        if parsed is not None:
            return parsed
    return None


class ChasterSessionCalendar(ChasterEntity, CalendarEntity):
    """Expose Chaster lock sessions as Home Assistant calendar events."""

    _attr_name = "Sessions"
    _attr_icon = "mdi:calendar-lock"

    def __init__(self, coordinator: ChasterCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_sessions_calendar"

    def _events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        seen: set[str] = set()

        for lock in self.coordinator.all_locks:
            lock_id = self.coordinator.lock_id(lock)
            if not lock_id or lock_id in seen:
                continue
            seen.add(lock_id)

            start = _first_datetime(
                lock, ("startDate", "startAt", "startedAt", "createdAt")
            )
            end = _first_datetime(
                lock,
                ("endDate", "endAt", "unlockDate", "unlockAt", "maxLimitDate"),
            )
            # Calendar events need a real interval; don't fabricate dates when
            # the API doesn't provide a session start or end.
            if start is None or end is None or end <= start:
                continue

            title = str(
                lock.get("customWearerName")
                or lock.get("title")
                or lock.get("name")
                or f"Chaster session {lock_id}"
            )
            status = lock.get("status") or lock.get("state") or "unknown"
            events.append(
                CalendarEvent(
                    summary=title,
                    start=start,
                    end=end,
                    description=f"Chaster session\nStatus: {status}\nLock ID: {lock_id}",
                    uid=f"chaster-{lock_id}",
                )
            )

        return sorted(events, key=lambda event: event.start)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next ongoing or upcoming session."""
        now = datetime.now(timezone.utc)
        return next(
            (event for event in self._events() if event.end > now),
            None,
        )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return Chaster sessions overlapping the requested calendar range."""
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
    """Set up the Chaster sessions calendar."""
    coordinator: ChasterCoordinator = hass.data[entry.domain][entry.entry_id]
    async_add_entities([ChasterSessionCalendar(coordinator)])
