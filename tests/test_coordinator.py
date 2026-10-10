"""Regression tests for coordinator lock selection and keyholder response shapes."""

from __future__ import annotations

from pathlib import Path
import importlib
import sys
import types
import unittest


def _module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


# Import the coordinator without requiring a full Home Assistant installation.
ha = _module("homeassistant")
ha.__path__ = getattr(ha, "__path__", [])  # type: ignore[attr-defined]
core = _module("homeassistant.core")
core.HomeAssistant = getattr(core, "HomeAssistant", type("HomeAssistant", (), {}))  # type: ignore[attr-defined]
helpers = _module("homeassistant.helpers")
helpers.__path__ = getattr(helpers, "__path__", [])  # type: ignore[attr-defined]
storage = _module("homeassistant.helpers.storage")
storage.Store = getattr(storage, "Store", type("Store", (), {}))  # type: ignore[attr-defined]
update_coordinator = _module("homeassistant.helpers.update_coordinator")


class _DataUpdateCoordinator:
    def __init__(self, *args, **kwargs):
        self.data = None


update_coordinator.DataUpdateCoordinator = getattr(
    update_coordinator, "DataUpdateCoordinator", _DataUpdateCoordinator
)  # type: ignore[attr-defined]
update_coordinator.UpdateFailed = getattr(
    update_coordinator, "UpdateFailed", type("UpdateFailed", (Exception,), {})
)  # type: ignore[attr-defined]

package_name = "custom_components.chaster"
package = sys.modules.get(package_name)
if package is None:
    package = types.ModuleType(package_name)
    sys.modules[package_name] = package
package_path = str(Path(__file__).resolve().parents[1] / "custom_components" / "chaster")
package.__path__ = [package_path]  # type: ignore[attr-defined]

const = importlib.import_module(f"{package_name}.const")
for name, value in {
    "API_BASE": "https://api.example.test",
    "DEFAULT_SCAN_INTERVAL": 60,
    "ROLE_AUTO": "auto",
    "ROLE_WEARER": "wearer",
    "ROLE_KEYHOLDER": "keyholder",
    "ROLE_BOTH": "both",
}.items():
    if not hasattr(const, name):
        setattr(const, name, value)

coordinator_module = importlib.import_module(f"{package_name}.coordinator")
ChasterCoordinator = coordinator_module.ChasterCoordinator


class KeyholderLockSelectionTests(unittest.TestCase):
    def coordinator(self, data):
        coordinator = object.__new__(ChasterCoordinator)
        coordinator.data = data
        return coordinator

    def test_nested_keyholder_lock_is_detected_as_current(self):
        nested_lock = {
            "id": "lock-keyholder-1",
            "status": "locked",
            "startDate": "2030-01-01T00:00:00Z",
        }
        coordinator = self.coordinator({
            "locks": [],
            "keyholder": {
                "items": [
                    {
                        "id": "relationship-1",
                        "status": "accepted",
                        "lock": nested_lock,
                    }
                ]
            },
        })

        self.assertEqual(coordinator.current_lock, nested_lock)

    def test_flat_keyholder_lock_is_detected_as_current(self):
        lock = {
            "id": "lock-keyholder-flat",
            "status": "active",
            "startDate": "2030-01-01T00:00:00Z",
        }
        coordinator = self.coordinator({
            "locks": [],
            "keyholder": {"items": [lock]},
        })

        self.assertEqual(coordinator.current_lock, lock)

    def test_inactive_nested_keyholder_lock_is_not_current(self):
        coordinator = self.coordinator({
            "locks": [],
            "keyholder": {
                "items": [
                    {
                        "id": "relationship-ended",
                        "status": "accepted",
                        "lock": {"id": "lock-ended", "status": "unlocked"},
                    }
                ]
            },
        })

        self.assertIsNone(coordinator.current_lock)

    def test_keyholder_collection_accepts_dict_of_relationships(self):
        lock = {"id": "lock-keyholder-map", "status": "locked"}
        coordinator = self.coordinator({
            "locks": [],
            "keyholder": {
                "items": {
                    "relationship-1": {"id": "relationship-1", "lock": lock}
                }
            },
        })

        self.assertEqual(coordinator.current_lock, lock)


if __name__ == "__main__":
    unittest.main()
