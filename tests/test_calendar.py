"""Regression tests for Chaster calendar timing, history, and role separation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
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

ha_util = _module("homeassistant.util")
ha_util.__path__ = []  # type: ignore[attr-defined]
dt_util = _module("homeassistant.util.dt")
dt_util.as_local = lambda value: value.astimezone(timezone.utc)  # type: ignore[attr-defined]
sys.modules[dt_util.__name__] = dt_util

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
        self.update_interval = timedelta(minutes=5)

    @staticmethod
    def _dict_list(value):
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def lock_id(lock):
        if not isinstance(lock, dict):
            return None
        for key in ("id", "_id", "lockId", "lock_id", "sessionId", "session_id"):
            if lock.get(key) is not None:
                return str(lock[key])
        nested = lock.get("lock")
        if isinstance(nested, dict):
            return _Coordinator.lock_id(nested)
        return None

    @staticmethod
    def is_active(lock):
        return str(lock.get("status", lock.get("state", ""))).lower() in {
            "locked", "active", "running"
        }


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
_first_number = calendar_integration._first_number


def _calendar(data, role="wearer"):
    calendar = object.__new__(ChasterSessionCalendar)
    calendar.coordinator = _Coordinator(data)
    calendar.role = role
    return calendar


class CalendarTimerDateTests(unittest.TestCase):
    def test_parses_iso_and_unix_timestamps(self):
        expected = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(_parse_datetime("2030-01-01T00:00:00Z"), expected)
        self.assertEqual(_parse_datetime(1_893_456_000), expected)

    def test_parses_millisecond_unix_timestamp(self):
        expected = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(_parse_datetime(1_893_456_000_000), expected)

    def test_parses_negative_millisecond_unix_timestamp(self):
        expected = datetime.fromtimestamp(-1_000_000_000, tz=timezone.utc)
        self.assertEqual(_parse_datetime(-1_000_000_000_000), expected)

    def test_naive_iso_date_is_treated_as_utc(self):
        self.assertEqual(
            _parse_datetime("2030-01-01T00:00:00"),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        )

    def test_iso_offset_is_preserved_as_same_instant(self):
        self.assertEqual(
            _parse_datetime("2030-01-01T01:00:00+01:00"),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        )

    def test_invalid_and_out_of_range_dates_are_ignored(self):
        for value in (None, True, "", "not-a-date", float("inf"), 1e300, 10**1000):
            with self.subTest(value=value):
                self.assertIsNone(_parse_datetime(value))

    def test_reads_nested_timer_end_date(self):
        expected = datetime(2030, 1, 2, tzinfo=timezone.utc)
        self.assertEqual(
            _first_datetime(
                {"timer": {"endDate": "2030-01-02T00:00:00Z"}},
                ("endDate", "endAt"),
            ),
            expected,
        )

    def test_timer_numbers_reject_nonfinite_negative_and_boolean_values(self):
        for value in (float("inf"), float("-inf"), float("nan"), -1, True, 10**1000):
            with self.subTest(value=value):
                self.assertIsNone(_first_number(
                    {"timer": {"remainingSeconds": value}}, ("remainingSeconds",)
                ))

    def test_event_falls_back_to_absolute_end_when_remaining_value_overflows(self):
        lock = {
            "id": "lock-large-timer",
            "startDate": "2030-01-01T00:00:00Z",
            "endDate": "2030-01-03T00:00:00Z",
            "timer": {"remainingSeconds": 1e300},
            "status": "completed",
        }
        calendar = _calendar({
            "locks": [lock],
            "last_update_success_time": datetime(2030, 1, 1, tzinfo=timezone.utc),
        })
        event = calendar._events()[0]
        self.assertEqual(event.end, datetime(2030, 1, 3, tzinfo=timezone.utc))

    def test_event_end_tracks_updated_live_timer_but_uid_stays_stable(self):
        lock = {
            "id": "lock-1",
            "startDate": "2030-01-01T00:00:00Z",
            "timer": {"endDate": "2030-01-02T00:00:00Z"},
            "title": "First title",
            "status": "locked",
        }
        calendar = _calendar({"locks": [lock]})
        first_event = calendar._events()[0]
        lock["timer"]["endDate"] = "2030-01-04T00:00:00Z"
        lock["title"] = "Updated title"
        second_events = calendar._events()

        self.assertEqual(first_event.end.isoformat(), "2030-01-02")
        self.assertEqual(len(second_events), 3)
        self.assertEqual(second_events[-1].end.isoformat(), "2030-01-04")
        self.assertEqual(first_event.uid, second_events[0].uid)
        self.assertEqual(
            second_events[0].summary,
            "Chaster — Active session — started 00:00",
        )

    def test_active_session_is_split_into_daily_events(self):
        from unittest.mock import patch

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                current = cls(2030, 1, 2, 12, 0, tzinfo=timezone.utc)
                return current.astimezone(tz) if tz else current.replace(tzinfo=None)

        calendar = _calendar({"locks": [{
            "id": "multi-day",
            "startDate": "2030-01-01T13:38:00Z",
            "endDate": "2030-01-04T13:38:00Z",
            "status": "locked",
        }]})
        with patch.object(calendar_integration, "datetime", FixedDateTime):
            events = calendar._events()

        self.assertEqual(len(events), 4)
        self.assertEqual(
            [event.summary for event in events],
            [
                "Chaster — Active session — started 13:38",
                "Chaster — Active session",
                "Chaster — Active session",
                "Chaster — Active session",
            ],
        )
        self.assertEqual(events[0].start.isoformat(), "2030-01-01")
        self.assertEqual(events[0].end.isoformat(), "2030-01-02")
        self.assertEqual(events[1].start.isoformat(), "2030-01-02")
        self.assertEqual(events[1].end.isoformat(), "2030-01-03")
        self.assertEqual(events[2].end.isoformat(), "2030-01-04")
        self.assertEqual(events[3].start.isoformat(), "2030-01-04")
        self.assertEqual(events[3].end.isoformat(), "2030-01-05")
        self.assertEqual(len({event.uid for event in events}), 4)

    def test_duplicate_lock_ids_produce_one_event_and_fresh_record_wins(self):
        older = {
            "id": "same-lock",
            "startDate": "2030-01-01T00:00:00Z",
            "endDate": "2030-01-02T00:00:00Z",
            "title": "Old",
        }
        fresh = {**older, "endDate": "2030-01-03T00:00:00Z", "title": "Fresh"}
        calendar = _calendar({"locks": [older, fresh]})
        events = calendar._events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].summary, "Fresh")
        self.assertEqual(events[0].end, datetime(2030, 1, 3, tzinfo=timezone.utc))

    def test_missing_id_and_malformed_or_missing_dates_are_skipped(self):
        calendar = _calendar({"locks": [
            {"startDate": "2030-01-01T00:00:00Z", "endDate": "2030-01-02T00:00:00Z"},
            {"id": "bad-date", "startDate": "broken", "endDate": "2030-01-02T00:00:00Z"},
            {"id": "no-end", "startDate": "2030-01-01T00:00:00Z"},
        ]})
        self.assertEqual(calendar._events(), [])

    def test_historical_ended_lock_remains_a_calendar_event(self):
        calendar = _calendar({"locks": [{
            "id": "historic",
            "startDate": "2030-01-01T00:00:00Z",
            "endDate": "2030-01-02T00:00:00Z",
            "status": "ended",
        }]})
        event = calendar._events()[0]
        self.assertEqual(event.uid, "chaster-wearer-historic")
        self.assertIn("Status: ended", event.description)

    def test_keyholder_nested_lock_is_unwrapped_and_kept_role_specific(self):
        lock = {
            "id": "shared-lock-id",
            "startDate": "2030-01-01T00:00:00Z",
            "endDate": "2030-01-02T00:00:00Z",
            "title": "Keyholder session",
        }
        data = {
            "locks": [],
            "current_lock": lock,
            "keyholder": {"items": [{"id": "relationship-1", "lock": lock}]},
        }
        wearer_events = _calendar(data, "wearer")._events()
        keyholder_events = _calendar(data, "keyholder")._events()
        self.assertEqual(len(wearer_events), 0)
        self.assertEqual(len(keyholder_events), 1)
        self.assertEqual(keyholder_events[0].uid, "chaster-keyholder-shared-lock-id")

    def test_keyholder_and_wearer_same_id_have_distinct_uids(self):
        lock = {
            "id": "same-id",
            "startDate": "2030-01-01T00:00:00Z",
            "endDate": "2030-01-02T00:00:00Z",
        }
        wearer = _calendar({"locks": [lock]}, "wearer")._events()[0]
        keyholder = _calendar({"keyholder": {"items": [{"lock": lock}]}}, "keyholder")._events()[0]
        self.assertNotEqual(wearer.uid, keyholder.uid)

    def test_expired_expected_end_is_extended_while_lock_is_active(self):
        lock = {
            "id": "lock-overdue",
            "startDate": "2020-01-01T10:00:00Z",
            "endDate": "2020-01-01T12:30:00Z",
            "status": "locked",
        }
        events = _calendar({"locks": [lock]})._events()
        self.assertGreater(max(event.end for event in events), datetime.now(timezone.utc).date())

    def test_overdue_ended_lock_is_not_artificially_extended(self):
        lock = {
            "id": "lock-ended",
            "startDate": "2020-01-01T10:00:00Z",
            "endDate": "2020-01-01T12:30:00Z",
            "status": "ended",
        }
        event = _calendar({"locks": [lock]})._events()[0]
        self.assertEqual(event.end, datetime(2020, 1, 1, 12, 30, tzinfo=timezone.utc))

    def test_event_end_uses_remaining_time_anchored_to_refresh(self):
        refreshed_at = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        lock = {
            "id": "lock-live",
            "startDate": "2030-01-01T10:00:00Z",
            "endDate": "2030-01-01T12:30:00Z",
            "timer": {"timeRemainingSeconds": 3600},
            "status": "locked",
        }
        calendar = _calendar({
            "locks": [lock],
            "last_update_success_time": refreshed_at,
        })
        event = calendar._events()[0]
        # Active sessions are exposed as all-day calendar events. The live
        # timer still determines the event's daily segmentation, not its
        # intraday end timestamp.
        self.assertEqual(event.end.isoformat(), "2030-01-02")

    def test_calendar_range_uses_strict_overlap_boundaries(self):
        locks = [
            {"id": "before", "startDate": "2030-01-01T08:00:00Z", "endDate": "2030-01-01T09:00:00Z"},
            {"id": "overlap", "startDate": "2030-01-01T08:59:00Z", "endDate": "2030-01-01T10:01:00Z"},
            {"id": "after", "startDate": "2030-01-01T10:00:00Z", "endDate": "2030-01-01T11:00:00Z"},
        ]
        calendar = _calendar({"locks": locks})
        events = asyncio.run(calendar.async_get_events(
            None,
            datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc),
            datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc),
        ))
        self.assertEqual([event.uid for event in events], ["chaster-wearer-overlap"])


if __name__ == "__main__":
    unittest.main()
