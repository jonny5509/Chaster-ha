"""Regression tests for live Chaster calendar timer dates."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
import sys
import types
import unittest


# The calendar date helpers are intentionally tested without installing the
# Home Assistant runtime in this lightweight CI suite.
def _module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


ha = _module("homeassistant")
ha.__path__ = []  # type: ignore[attr-defined]
components = _module("homeassistant.components")
components.__path__ = []  # type: ignore[attr-defined]
calendar_module = _module("homeassistant.components.calendar")


class _CalendarEvent:
    def __init__(self, *, summary, start, end, description, uid):
        self.summary = summary
        self.start = start
        self.end = end
        self.description = description
        self.uid = uid


class _CalendarEntity:
    pass


calendar_module.CalendarEntity = _CalendarEntity  # type: ignore[attr-defined]
calendar_module.CalendarEvent = _CalendarEvent  # type: ignore[attr-defined]

config_entries = _module("homeassistant.config_entries")
config_entries.ConfigEntry = type("ConfigEntry", (), {})  # type: ignore[attr-defined]
core = _module("homeassistant.core")
core.HomeAssistant = type("HomeAssistant", (), {})  # type: ignore[attr-defined]

package_name = "custom_components.chaster"
if package_name not in sys.modules:
    package = types.ModuleType(package_name)
    package.__path__ = []  # type: ignore[attr-defined]
    sys.modules[package_name] = package

coordinator_module = types.ModuleType(f"{package_name}.coordinator")


class _Coordinator:
    def __init__(self, data):
        self.data = data
        self.current_lock = data.get("current_lock")
        self.last_update_success_time = data.get("last_update_success_time")

    @staticmethod
    def _dict_list(value):
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def lock_id(lock):
        return str(lock["id"]) if isinstance(lock, dict) and lock.get("id") else None


coordinator_module.ChasterCoordinator = _Coordinator  # type: ignore[attr-defined]
sys.modules[coordinator_module.__name__] = coordinator_module

entity_module = types.ModuleType(f"{package_name}.entity")


class _ChasterEntity:
    def __init__(self, coordinator, role=None):
        self.coordinator = coordinator


entity_module.ChasterEntity = _ChasterEntity  # type: ignore[attr-defined]
sys.modules[entity_module.__name__] = entity_module

calendar_integration = importlib.import_module(f"{package_name}.calendar")
ChasterSessionCalendar = calendar_integration.ChasterSessionCalendar
_parse_datetime = calendar_integration._parse_datetime
_first_datetime = calendar_integration._first_datetime


class CalendarTimerDateTests(unittest.TestCase):
    def test_parses_iso_and_unix_timestamps(self):
        expected = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(_parse_datetime("2030-01-01T00:00:00Z"), expected)
        self.assertEqual(_parse_datetime(1_893_456_000), expected)

    def test_reads_nested_timer_end_date(self):
        expected = datetime(2030, 1, 2, tzinfo=timezone.utc)
        self.assertEqual(
            _first_datetime(
                {"timer": {"endDate": "2030-01-02T00:00:00Z"}},
                ("endDate", "endAt"),
            ),
            expected,
        )

    def test_event_end_tracks_updated_live_timer(self):
        lock = {
            "id": "lock-1",
            "startDate": "2030-01-01T00:00:00Z",
            "timer": {"endDate": "2030-01-02T00:00:00Z"},
            "status": "locked",
        }
        coordinator = _Coordinator({"locks": [lock]})
        calendar = object.__new__(ChasterSessionCalendar)
        calendar.coordinator = coordinator
        calendar.role = "wearer"

        first_event = calendar._events()[0]
        lock["timer"]["endDate"] = "2030-01-04T00:00:00Z"
        second_event = calendar._events()[0]

        self.assertEqual(first_event.end, datetime(2030, 1, 2, tzinfo=timezone.utc))
        self.assertEqual(second_event.end, datetime(2030, 1, 4, tzinfo=timezone.utc))


    def test_event_end_uses_remaining_time_anchored_to_refresh(self):
        refreshed_at = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        lock = {
            "id": "lock-live",
            "startDate": "2030-01-01T10:00:00Z",
            "endDate": "2030-01-01T12:30:00Z",
            "timer": {"timeRemainingSeconds": 3600},
            "status": "locked",
        }
        coordinator = _Coordinator({
            "locks": [lock],
            "last_update_success_time": refreshed_at,
        })
        calendar = object.__new__(ChasterSessionCalendar)
        calendar.coordinator = coordinator
        calendar.role = "wearer"

        event = calendar._events()[0]
        self.assertEqual(event.end, datetime(2030, 1, 1, 13, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
