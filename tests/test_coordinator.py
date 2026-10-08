from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.chaster.coordinator import ChasterCoordinator


def test_lock_id_and_collection_normalization() -> None:
    assert ChasterCoordinator.lock_id({"id": 123}) == "123"
    assert ChasterCoordinator.lock_id({"lock": {"_id": "abc"}}) == "abc"
    assert ChasterCoordinator._dict_list({"items": [{"id": "1"}]}) == [{"id": "1"}]


def test_is_active_uses_status_and_dates() -> None:
    assert ChasterCoordinator.is_active({"status": "locked"})
    assert not ChasterCoordinator.is_active({"status": "archived"})
    now = datetime.now(timezone.utc)
    assert ChasterCoordinator.is_active({
        "startDate": (now - timedelta(minutes=1)).isoformat(),
        "endDate": (now + timedelta(minutes=1)).isoformat(),
    })
