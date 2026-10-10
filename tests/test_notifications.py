"""Regression tests for Chaster notification date parsing and role handling."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types
import unittest


def _module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


# Lightweight Home Assistant stubs keep these helper tests runnable in CI
# without requiring a full Home Assistant installation.
ha = _module("homeassistant")
ha.__path__ = getattr(ha, "__path__", [])  # type: ignore[attr-defined]
core = _module("homeassistant.core")
core.HomeAssistant = getattr(core, "HomeAssistant", type("HomeAssistant", (), {}))  # type: ignore[attr-defined]
config_entries = _module("homeassistant.config_entries")
config_entries.ConfigEntry = getattr(config_entries, "ConfigEntry", type("ConfigEntry", (), {}))  # type: ignore[attr-defined]
helpers = _module("homeassistant.helpers")
helpers.__path__ = getattr(helpers, "__path__", [])  # type: ignore[attr-defined]
event = _module("homeassistant.helpers.event")
event.async_track_time_interval = getattr(event, "async_track_time_interval", lambda *args, **kwargs: lambda: None)  # type: ignore[attr-defined]
storage = _module("homeassistant.helpers.storage")
storage.Store = getattr(storage, "Store", type("Store", (), {}))  # type: ignore[attr-defined]

package_name = "custom_components.chaster"
package = _module(package_name)
package_path = Path(__file__).resolve().parents[1] / "custom_components" / "chaster"
package.__path__ = [str(package_path)]  # type: ignore[attr-defined]

const = importlib.import_module(f"{package_name}.const")
for name, value in {
    "CONF_ENABLE_NOTIFICATIONS": "enable_notifications",
    "CONF_NOTIFICATION_SERVICE": "notification_service",
    "CONF_NOTIFY_COMPLETION": "notify_lock_completion",
    "CONF_NOTIFY_DAILY": "notify_daily_congratulations",
    "CONF_NOTIFY_KEYHOLDER": "notify_keyholder_locks",
    "CONF_NOTIFY_WEARER": "notify_wearer_locks",
    "DEFAULT_NOTIFICATION_SERVICE": "notify.notify",
    "DOMAIN": "chaster",
}.items():
    if not hasattr(const, name):
        setattr(const, name, value)

coordinator_module = _module(f"{package_name}.coordinator")
if not hasattr(coordinator_module, "ChasterCoordinator"):
    class _Coordinator:
        @staticmethod
        def _dict_list(value):
            return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

        @staticmethod
        def lock_id(item):
            if not isinstance(item, dict):
                return None
            if item.get("id") is not None:
                return str(item["id"])
            nested = item.get("lock")
            return _Coordinator.lock_id(nested) if isinstance(nested, dict) else None

    coordinator_module.ChasterCoordinator = _Coordinator  # type: ignore[attr-defined]

module_name = f"{package_name}._notifications_under_test"
spec = spec_from_file_location(module_name, package_path / "notifications.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load notifications module for regression tests")
notifications_module = module_from_spec(spec)
sys.modules[module_name] = notifications_module
spec.loader.exec_module(notifications_module)

_parse_datetime = notifications_module._parse_datetime
_first_date = notifications_module._first_date
_role_locks = notifications_module._role_locks


class NotificationDateTests(unittest.TestCase):
    def test_parses_iso_offset_as_utc(self):
        self.assertEqual(
            _parse_datetime("2030-01-01T01:00:00+01:00"),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        )

    def test_parses_unix_milliseconds(self):
        self.assertEqual(
            _parse_datetime(1_893_456_000_000),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        )

    def test_ignores_invalid_timestamps(self):
        for value in (None, True, "", "not-a-date", float("inf"), 1e300):
            with self.subTest(value=value):
                self.assertIsNone(_parse_datetime(value))

    def test_reads_nested_timer_start_date(self):
        self.assertEqual(
            _first_date(
                {"timer": {"startDate": "2030-01-01T00:00:00Z"}},
                ("startDate",),
            ),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        )

    def test_keyholder_lock_is_unwrapped_and_keeps_lock_id(self):
        lock = {"id": "lock-1", "startDate": "2030-01-01T00:00:00Z"}
        coordinator = type(
            "Coordinator",
            (),
            {
                "data": {"keyholder": {"items": [{"id": "relationship-1", "lock": lock}]}},
                "_dict_list": staticmethod(lambda value: value if isinstance(value, list) else []),
                "lock_id": staticmethod(lambda item: item.get("id") if isinstance(item, dict) else None),
            },
        )()
        locks = _role_locks(coordinator, "keyholder")
        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]["id"], "lock-1")
        self.assertEqual(locks[0]["startDate"], "2030-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
