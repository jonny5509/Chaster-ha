"""Configurable elapsed-day and lock-completion notifications."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import (
    CONF_ENABLE_NOTIFICATIONS,
    CONF_NOTIFICATION_SERVICE,
    CONF_NOTIFY_COMPLETION,
    CONF_NOTIFY_DAILY,
    CONF_NOTIFY_KEYHOLDER,
    CONF_NOTIFY_WEARER,
    DEFAULT_NOTIFICATION_SERVICE,
    DOMAIN,
)
from .coordinator import ChasterCoordinator

_LOGGER = logging.getLogger(__name__)
_CHECK_INTERVAL = timedelta(minutes=1)


def _parse_datetime(value: Any) -> datetime | None:
    """Parse supported Chaster dates as UTC-aware datetimes."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if abs(timestamp) >= 100_000_000_000:
                timestamp /= 1000
            parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
        else:
            return None
        return parsed
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _first_date(lock: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    """Find a date in the lock or its common nested timing objects."""
    for source in (lock, lock.get("timer"), lock.get("timing"), lock.get("dates")):
        if isinstance(source, dict):
            for key in keys:
                parsed = _parse_datetime(source.get(key))
                if parsed is not None:
                    return parsed
    return None


def _lock_name(lock: dict[str, Any], lock_id: str) -> str:
    """Return a readable lock name for notification messages."""
    return str(
        lock.get("customWearerName")
        or lock.get("title")
        or lock.get("name")
        or f"Chaster lock {lock_id}"
    )


def _role_locks(coordinator: ChasterCoordinator, role: str) -> list[dict[str, Any]]:
    """Return lock records for one role, unwrapping keyholder associations."""
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    if role == "wearer":
        source = coordinator._dict_list(data.get("locks"))
    else:
        keyholder = data.get("keyholder")
        if not isinstance(keyholder, dict):
            return []
        items = (
            keyholder.get("items")
            or keyholder.get("locks")
            or keyholder.get("results")
            or keyholder.get("data")
            or []
        )
        if isinstance(items, dict):
            items = list(items.values())
        source = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                nested = item.get("lock")
                source.append({**item, **nested} if isinstance(nested, dict) else item)

    by_id: dict[str, dict[str, Any]] = {}
    for lock in source:
        lock_id = coordinator.lock_id(lock)
        if lock_id:
            by_id[lock_id] = lock
    return list(by_id.values())


class ChasterLockNotifications:
    """Send configurable milestone and completion notifications once per lock."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: ChasterCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.options = entry.options
        self.service = str(
            self.options.get(CONF_NOTIFICATION_SERVICE, DEFAULT_NOTIFICATION_SERVICE)
        ).split(".", 1)[1]
        self.store = Store(hass, 1, f"{DOMAIN}_notifications_{entry.entry_id}")
        self.state: dict[str, dict[str, Any]] = {}

    async def async_start(self) -> None:
        """Load persistent delivery state and schedule checks."""
        saved = await self.store.async_load()
        if isinstance(saved, dict):
            locks = saved.get("locks")
            if isinstance(locks, dict):
                self.state = {
                    str(key): value
                    for key, value in locks.items()
                    if isinstance(value, dict)
                }

        async def _check(_now: datetime) -> None:
            await self.async_check()

        self.entry.async_on_unload(
            async_track_time_interval(self.hass, _check, _CHECK_INTERVAL)
        )
        # Check once immediately so setup does not wait for the next minute tick.
        await self.async_check()

    async def _notify(self, title: str, message: str) -> bool:
        """Deliver a notification using the configured Home Assistant notify service."""
        try:
            await self.hass.services.async_call(
                "notify",
                self.service,
                {"title": title, "message": message},
                blocking=True,
            )
            return True
        except Exception:  # Home Assistant services can raise several service errors.
            _LOGGER.exception(
                "Unable to send Chaster notification using notify.%s", self.service
            )
            return False

    async def async_check(self) -> None:
        """Check elapsed 24-hour milestones and newly ended locks."""
        data = self.coordinator.data
        if not isinstance(data, dict):
            return

        changed = False
        now = datetime.now(timezone.utc)
        role_settings = (
            ("wearer", CONF_NOTIFY_WEARER),
            ("keyholder", CONF_NOTIFY_KEYHOLDER),
        )

        for role, option in role_settings:
            if not self.options.get(option, True):
                continue
            for lock in _role_locks(self.coordinator, role):
                lock_id = self.coordinator.lock_id(lock)
                if not lock_id:
                    continue
                start = _first_date(
                    lock, ("startDate", "startAt", "startedAt", "createdAt")
                )
                if start is None or start > now:
                    continue

                state_key = f"{role}:{lock_id}"
                record = self.state.setdefault(
                    state_key,
                    {
                        "last_daily_day": 0,
                        "active_seen": False,
                        "completion_notified": False,
                    },
                )
                active = self.coordinator.is_active(lock)
                name = _lock_name(lock, lock_id)

                if active:
                    if not record.get("active_seen"):
                        record["active_seen"] = True
                        changed = True

                    elapsed_days = max(0, int((now - start).total_seconds() // 86400))
                    if (
                        self.options.get(CONF_NOTIFY_DAILY, True)
                        and elapsed_days >= 1
                        and elapsed_days > int(record.get("last_daily_day", 0))
                    ):
                        message = (
                            f"🎉 Congratulations! You've completed {elapsed_days} "
                            f"{'day' if elapsed_days == 1 else 'days'} of {name}. Keep it going!"
                        )
                        if await self._notify("Chaster daily congratulations", message):
                            record["last_daily_day"] = elapsed_days
                            changed = True
                elif record.get("active_seen") and not record.get("completion_notified"):
                    if self.options.get(CONF_NOTIFY_COMPLETION, True):
                        elapsed_days = max(0, int((now - start).total_seconds() // 86400))
                        message = (
                            f"🏆 Congratulations! {name} has ended after {elapsed_days} "
                            f"{'day' if elapsed_days == 1 else 'days'}. Well done!"
                        )
                        if await self._notify("Chaster lock completed", message):
                            record["completion_notified"] = True
                            changed = True

        if changed:
            await self.store.async_save({"locks": self.state})


async def async_setup_notifications(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: ChasterCoordinator,
) -> None:
    """Set up notification tracking when enabled in the integration options."""
    if not entry.options.get(CONF_ENABLE_NOTIFICATIONS, False):
        return

    service = entry.options.get(CONF_NOTIFICATION_SERVICE, DEFAULT_NOTIFICATION_SERVICE)
    if not isinstance(service, str) or not vol.match(r"^notify\.[a-z0-9_]+$")(service):
        _LOGGER.warning("Chaster notifications are enabled but the notify service is invalid")
        return

    await ChasterLockNotifications(hass, entry, coordinator).async_start()
