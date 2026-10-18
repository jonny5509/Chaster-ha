"""Consistent, restart-safe notifications for wearer and keyholder locks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import (
    CONF_ENABLE_PHONE_NOTIFICATIONS,
    CONF_ENABLE_HA_NOTIFICATIONS,
    CONF_NOTIFICATION_DESTINATION,
    CONF_NOTIFICATION_SERVICE,
    CONF_NOTIFICATION_TARGETS,
    CONF_NOTIFY_KEYHOLDER,
    CONF_NOTIFY_WEARER,
    CONF_NOTIFY_DAILY,
    CONF_NOTIFY_COMPLETION,
    DEFAULT_NOTIFICATION_SERVICE,
    DOMAIN,
)
from .coordinator import ChasterCoordinator

_LOGGER = logging.getLogger(__name__)
_CHECK_INTERVAL = timedelta(minutes=1)
_PHONE_SERVICE = re.compile(r"notify\.mobile_app_[a-z0-9_]+")
_DAY_SECONDS = 86400


def _parse_datetime(value: Any) -> datetime | None:
    """Parse API timestamps as UTC-aware datetimes."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if abs(timestamp) >= 100_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (OverflowError, OSError, TypeError, ValueError):
        return None
    return None


def _first_date(lock: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    """Find a timestamp on the lock or in common nested timing objects."""
    for source in (lock, lock.get("timer"), lock.get("timing"), lock.get("dates")):
        if isinstance(source, dict):
            for key in keys:
                parsed = _parse_datetime(source.get(key))
                if parsed is not None:
                    return parsed
    return None


def _destination(options: dict[str, Any]) -> str:
    """Normalize current and legacy destination option values."""
    value = options.get(CONF_NOTIFICATION_DESTINATION)
    if value == "ha":
        value = "home_assistant"
    if value in {"none", "home_assistant", "phone", "both"}:
        return value
    phone = options.get(CONF_ENABLE_PHONE_NOTIFICATIONS, False)
    ha = options.get(CONF_ENABLE_HA_NOTIFICATIONS, False)
    return "both" if phone and ha else "phone" if phone else "home_assistant" if ha else "none"


def _phone_targets(options: dict[str, Any]) -> list[str]:
    """Return unique mobile-app notify services, including legacy settings."""
    targets = options.get(CONF_NOTIFICATION_TARGETS)
    if isinstance(targets, str):
        targets = [targets]
    if targets is None:
        targets = [options.get(CONF_NOTIFICATION_SERVICE, DEFAULT_NOTIFICATION_SERVICE)]
    services: list[str] = []
    for target in targets if isinstance(targets, list) else []:
        if not isinstance(target, str):
            continue
        service = target if target.startswith("notify.") else f"notify.{target}"
        if _PHONE_SERVICE.fullmatch(service) and service not in services:
            services.append(service)
    return services


def _duration(days: int) -> str:
    return f"{days} day" if days == 1 else f"{days} days"


def _lock_id(coordinator: ChasterCoordinator, lock: dict[str, Any]) -> str | None:
    return coordinator.lock_id(lock)


def _lock_name(lock: dict[str, Any], lock_id: str) -> str:
    return str(lock.get("customWearerName") or lock.get("title") or lock.get("name") or f"Chaster lock {lock_id}")


def _role_locks(coordinator: ChasterCoordinator, role: str) -> list[dict[str, Any]]:
    """Return lock records for a role, unwrapping keyholder associations."""
    data = coordinator.data if isinstance(coordinator.data, dict) else {}
    if role == "wearer":
        source = coordinator._dict_list(data.get("locks"))
    else:
        keyholder = data.get("keyholder")
        if not isinstance(keyholder, dict):
            return []
        items = keyholder.get("items") or keyholder.get("locks") or keyholder.get("results") or keyholder.get("data") or []
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
        lock_id = _lock_id(coordinator, lock)
        if lock_id:
            by_id[lock_id] = lock
    return list(by_id.values())


class ChasterLockNotifications:
    """Send consistent milestones and completion notifications once per lock."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: ChasterCoordinator) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.options = entry.options
        self.store = Store(hass, 1, f"{DOMAIN}_notifications_{entry.entry_id}")
        self.state: dict[str, dict[str, Any]] = {}

    async def async_start(self) -> None:
        saved = await self.store.async_load()
        if isinstance(saved, dict) and isinstance(saved.get("locks"), dict):
            self.state = {
                str(key): value for key, value in saved["locks"].items() if isinstance(value, dict)
            }
        self.entry.async_on_unload(
            async_track_time_interval(self.hass, self._tick, _CHECK_INTERVAL)
        )
        await self.async_check()

    async def _tick(self, _now: datetime) -> None:
        await self.async_check()

    async def _notify(self, title: str, message: str, event: str, lock_key: str) -> bool:
        """Deliver one standard payload to every selected destination."""
        options = self.entry.options
        destination = _destination(options)
        delivered = False
        safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", lock_key)[:80]
        if destination in {"phone", "both"}:
            for service in _phone_targets(options):
                try:
                    domain, name = service.split(".", 1)
                    await self.hass.services.async_call(
                        domain, name, {"title": title, "message": message}, blocking=True
                    )
                    delivered = True
                except Exception:
                    _LOGGER.exception("Unable to send %s phone notification via %s", DOMAIN, service)
        if destination in {"home_assistant", "both"}:
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": title,
                        "message": message,
                        "notification_id": f"{DOMAIN}_{self.entry.entry_id}_{event}_{safe_key}",
                    },
                    blocking=True,
                )
                delivered = True
            except Exception:
                _LOGGER.exception("Unable to create %s Home Assistant notification", DOMAIN)
        return delivered

    async def async_check(self) -> None:
        if not isinstance(self.coordinator.data, dict):
            return
        now = datetime.now(timezone.utc)
        changed = False

        for role, option in (("wearer", CONF_NOTIFY_WEARER), ("keyholder", CONF_NOTIFY_KEYHOLDER)):
            if not self.options.get(option, False):
                continue
            for lock in _role_locks(self.coordinator, role):
                lock_id = _lock_id(self.coordinator, lock)
                if not lock_id:
                    continue
                start = _first_date(lock, ("startDate", "startAt", "startedAt", "createdAt"))
                if start is None or start > now:
                    continue

                lock_key = f"{role}:{lock_id}"
                record = self.state.setdefault(lock_key, {
                    "start": start.timestamp(),
                    "last_daily_day": 0,
                    "active_seen": False,
                    "completion_notified": False,
                })
                saved_start = _parse_datetime(record.get("start"))
                if saved_start is None or abs((saved_start - start).total_seconds()) > 60:
                    record.update({
                        "start": start.timestamp(),
                        "last_daily_day": 0,
                        "active_seen": False,
                        "completion_notified": False,
                    })
                    changed = True

                active = self.coordinator.is_active(lock)
                name = _lock_name(lock, lock_id)
                elapsed_days = max(0, int((now - start).total_seconds() // _DAY_SECONDS))

                if active:
                    if not record.get("active_seen"):
                        record["active_seen"] = True
                        changed = True
                    if (
                        _destination(self.entry.options) != "none"
                        and self.options.get(CONF_NOTIFY_DAILY, True)
                        and elapsed_days >= 1
                        and elapsed_days > int(record.get("last_daily_day", 0))
                    ):
                        title = "Session milestone reached"
                        message = f"🎉 Day {elapsed_days} complete for {name}. Keep it going!"
                        if await self._notify(title, message, "daily", lock_key):
                            record["last_daily_day"] = elapsed_days
                            changed = True
                elif record.get("active_seen") and not record.get("completion_notified"):
                    if _destination(self.entry.options) != "none" and self.options.get(CONF_NOTIFY_COMPLETION, True):
                        title = "Session completed"
                        message = f"🏆 {name} is complete after {_duration(elapsed_days)}. Well done!"
                        if await self._notify(title, message, "completion", lock_key):
                            record["completion_notified"] = True
                            changed = True
                    else:
                        record["completion_notified"] = True
                        changed = True
                    record["active_seen"] = False
                    changed = True

        if changed:
            await self.store.async_save({"locks": self.state})


async def async_setup_notifications(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: ChasterCoordinator
) -> None:
    """Start notification tracking only when at least one destination is enabled."""
    if _destination(entry.options) == "none":
        return
    await ChasterLockNotifications(hass, entry, coordinator).async_start()
