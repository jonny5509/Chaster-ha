"""Regression tests for Chaster API path and timer safety checks."""

from __future__ import annotations

from pathlib import Path
import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Load api.py without importing the integration's Home Assistant-dependent
# package initializer. The API client only needs API_BASE from const.py.
package_name = "custom_components.chaster"
if package_name not in sys.modules:
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "chaster")]  # type: ignore[attr-defined]
    sys.modules[package_name] = package
const_name = f"{package_name}.const"
if const_name not in sys.modules:
    const = types.ModuleType(const_name)
    const.API_BASE = "https://api.example.test"  # type: ignore[attr-defined]
    sys.modules[const_name] = const

api_module = importlib.import_module(f"{package_name}.api")
ChasterApi = api_module.ChasterApi
ChasterApiError = api_module.ChasterApiError


class ValidatePathTests(unittest.TestCase):
    def test_accepts_normal_api_paths(self) -> None:
        self.assertEqual(ChasterApi._validate_path("/locks"), "/locks")
        self.assertEqual(
            ChasterApi._validate_path("/locks/abc/extensions/def/action"),
            "/locks/abc/extensions/def/action",
        )

    def test_rejects_non_absolute_and_host_relative_paths(self) -> None:
        for path in ("locks", "//evil.example/path", ""):
            with self.subTest(path=path), self.assertRaises(ChasterApiError):
                ChasterApi._validate_path(path)

    def test_rejects_url_delimiters_controls_and_backslashes(self) -> None:
        for path in (
            "/locks?admin=true",
            "/locks#fragment",
            "/locks\\evil",
            "/locks/one\ntwo",
            "/locks/one\x7f",
        ):
            with self.subTest(path=path), self.assertRaises(ChasterApiError):
                ChasterApi._validate_path(path)

    def test_rejects_dot_segments_and_encoded_traversal(self) -> None:
        for path in (
            "/locks/../profile",
            "/./locks",
            "/locks/%2e%2e/profile",
            "/locks/%252e%252e/profile",
            "/locks/%2f%2fevil",
            "/locks/%5c%5cevil",
        ):
            with self.subTest(path=path), self.assertRaises(ChasterApiError):
                ChasterApi._validate_path(path)

    def test_identifier_must_be_a_single_safe_path_segment(self) -> None:
        self.assertEqual(ChasterApi._path_segment("abc-123"), "abc-123")
        for value in ("", ".", "..", "a/b", "a\\b", "a?b", "a#b", "a%b", "bad\nvalue", "bad\x7fvalue"):
            with self.subTest(value=value), self.assertRaises(ChasterApiError):
                ChasterApi._path_segment(value)


class UnlockSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.api = ChasterApi(session=None, token="test-token")
        self.api.lock = AsyncMock()  # type: ignore[method-assign]
        self.api.request = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]

    async def test_unlock_is_blocked_when_end_time_is_missing(self) -> None:
        self.api.lock.return_value = {"status": "locked"}
        with self.assertRaisesRegex(ChasterApiError, "no valid end time"):
            await self.api.unlock("lock-1")
        self.api.request.assert_not_awaited()

    async def test_unlock_is_blocked_when_end_time_is_invalid(self) -> None:
        self.api.lock.return_value = {"endDate": "not-a-date"}
        with self.assertRaisesRegex(ChasterApiError, "no valid end time"):
            await self.api.unlock("lock-1")
        self.api.request.assert_not_awaited()

    async def test_unlock_is_blocked_until_timer_expires(self) -> None:
        self.api.lock.return_value = {"endDate": "2030-01-01T00:00:00Z"}
        with patch("time.time", return_value=1_800_000_000):
            with self.assertRaisesRegex(ChasterApiError, "timer has not expired"):
                await self.api.unlock("lock-1")
        self.api.request.assert_not_awaited()

    async def test_unlock_is_allowed_after_timer_expires(self) -> None:
        self.api.lock.return_value = {"endDate": "2020-01-01T00:00:00Z"}
        with patch("time.time", return_value=1_900_000_000):
            result = await self.api.unlock("lock-1")
        self.assertEqual(result, {"ok": True})
        self.api.request.assert_awaited_once_with("POST", "/locks/lock-1/unlock")

    async def test_unlock_is_blocked_if_lock_response_is_not_an_object(self) -> None:
        self.api.lock.return_value = None
        with self.assertRaisesRegex(ChasterApiError, "Unable to verify lock timer"):
            await self.api.unlock("lock-1")
        self.api.request.assert_not_awaited()

    async def test_unlock_rejects_boolean_end_time(self) -> None:
        self.api.lock.return_value = {"endDate": True}
        with self.assertRaisesRegex(ChasterApiError, "no valid end time"):
            await self.api.unlock("lock-1")
        self.api.request.assert_not_awaited()

    async def test_unlock_rejects_non_finite_end_time(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.api.lock.return_value = {"endDate": value}
                with self.assertRaisesRegex(ChasterApiError, "no valid end time"):
                    await self.api.unlock("lock-1")
                self.api.request.assert_not_awaited()

    async def test_unlock_rejects_unsafe_lock_id(self) -> None:
        with self.assertRaisesRegex(ChasterApiError, "Invalid Chaster API lock identifier"):
            await self.api.unlock("../profile")
        self.api.lock.assert_not_awaited()
        self.api.request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
