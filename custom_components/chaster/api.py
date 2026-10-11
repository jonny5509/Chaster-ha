from __future__ import annotations

import asyncio
import math
import re
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import API_BASE

_REQUEST_TIMEOUT = ClientTimeout(total=20)
_UNSAFE_PATH_ENCODING = re.compile(r"%(?:25)*(?:2e|2f|5c)", re.IGNORECASE)


class ChasterApiError(Exception):
    """Chaster API error."""


class ChasterApi:
    """Small async client for the Chaster Public API."""

    def __init__(self, session: ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    @staticmethod
    def _validate_path(path: str) -> str:
        """Reject paths that could escape the configured Chaster API host."""
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or "\\" in path
            or "?" in path
            or "#" in path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
            or any(part in {".", ".."} for part in path.split("/"))
            or _UNSAFE_PATH_ENCODING.search(path)
        ):
            raise ChasterApiError("Invalid Chaster API path")
        return path

    @staticmethod
    def _path_segment(value: str, label: str = "identifier") -> str:
        """Encode one untrusted identifier as a single URL path segment."""
        if (
            not isinstance(value, str)
            or not value
            or value in {".", ".."}
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or any(char in value for char in ("/", "\\", "?", "#", "%"))
        ):
            raise ChasterApiError(f"Invalid Chaster API {label}")
        return quote(value, safe="-_.~")

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request using the developer token."""
        path = self._validate_path(path)

        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("Accept", "application/json")
        headers["Authorization"] = f"Bearer {self._token}"
        url = f"{API_BASE}{path}"
        kwargs.setdefault("timeout", _REQUEST_TIMEOUT)

        try:
            async with self._session.request(
                method.upper(), url, headers=headers, **kwargs
            ) as response:
                if response.status >= 400:
                    # Response bodies may contain private account data; don't log them.
                    raise ChasterApiError(
                        f"Chaster API returned HTTP {response.status}"
                    )
                if response.status == 204:
                    return None
                try:
                    return await response.json(content_type=None)
                except (ValueError, ClientError) as err:
                    raise ChasterApiError(
                        "Chaster API returned an invalid JSON response"
                    ) from err
        except asyncio.TimeoutError as err:
            raise ChasterApiError("Chaster API request timed out") from err
        except ClientError as err:
            raise ChasterApiError("Unable to connect to the Chaster API") from err

    async def profile(self) -> Any:
        return await self.request("GET", "/auth/profile")

    async def locks(self, status: str | None = None) -> Any:
        params = {"status": status} if status else None
        return await self.request("GET", "/locks", params=params)

    async def lock(self, lock_id: str) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request("GET", f"/locks/{lock_id}")

    async def keyholder_locks(self, payload: dict[str, Any] | None = None) -> Any:
        return await self.request(
            "POST",
            "/keyholder/locks/search",
            json=payload or {"status": "locked", "page": 0, "limit": 50},
        )

    async def lock_extension(self, lock_id: str, extension_id: str) -> Any:
        """Get information from an extension attached to a lock."""
        lock_id = self._path_segment(lock_id, "lock identifier")
        extension_id = self._path_segment(extension_id, "extension identifier")
        return await self.request(
            "GET", f"/locks/{lock_id}/extensions/{extension_id}"
        )

    async def lock_extension_action(
        self, lock_id: str, extension_id: str, payload: dict[str, Any]
    ) -> Any:
        """Trigger an action exposed by a lock extension."""
        lock_id = self._path_segment(lock_id, "lock identifier")
        extension_id = self._path_segment(extension_id, "extension identifier")
        return await self.request(
            "POST",
            f"/locks/{lock_id}/extensions/{extension_id}/action",
            json=payload,
        )

    async def shared_locks(self, status: str = "active") -> Any:
        return await self.request("GET", "/shared-locks", params={"status": status})

    async def conversations(self) -> Any:
        return await self.request("GET", "/conversations")

    async def conversation(self, conversation_id: str) -> Any:
        conversation_id = self._path_segment(conversation_id, "conversation identifier")
        return await self.request("GET", f"/conversations/{conversation_id}")

    async def send_message(self, conversation_id: str, payload: dict[str, Any]) -> Any:
        conversation_id = self._path_segment(conversation_id, "conversation identifier")
        return await self.request("POST", f"/conversations/{conversation_id}", json=payload)

    async def create_conversation(self, payload: dict[str, Any]) -> Any:
        return await self.request("POST", "/conversations", json=payload)

    async def update_time(self, lock_id: str, seconds: int) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request(
            "POST", f"/locks/{lock_id}/update-time", json={"duration": seconds}
        )

    async def freeze(self, lock_id: str, frozen: bool) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request(
            "POST", f"/locks/{lock_id}/freeze", json={"isFrozen": frozen}
        )

    async def unlock(self, lock_id: str) -> Any:
        """Unlock a lock only after its timer has expired."""
        from datetime import datetime, timezone

        lock_id = self._path_segment(lock_id, "lock identifier")
        lock = await self.lock(lock_id)
        if not isinstance(lock, dict):
            raise ChasterApiError("Unable to verify lock timer before unlock")

        end_time = None
        for key in ("endDate", "endAt", "unlockDate", "unlockAt"):
            value = lock.get(key)
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                timestamp = float(value)
                if not math.isfinite(timestamp):
                    continue
                if abs(timestamp) >= 10000000000:
                    timestamp /= 1000
                end_time = timestamp
                break
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    timestamp = parsed.timestamp()
                    if math.isfinite(timestamp):
                        end_time = timestamp
                        break
                except (ValueError, OverflowError, OSError):
                    continue

        if end_time is None:
            raise ChasterApiError("Lock has no valid end time; unlock is blocked")
        import time

        if time.time() < end_time:
            raise ChasterApiError("Lock timer has not expired; unlock is blocked")

        return await self.request("POST", f"/locks/{lock_id}/unlock")

    async def emergency_unlock(self, lock_id: str) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request("POST", f"/locks/{lock_id}/emergency-unlock", json={})

    async def archive(self, lock_id: str, keyholder: bool = False) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        suffix = "/archive/keyholder" if keyholder else "/archive"
        return await self.request("POST", f"/locks/{lock_id}{suffix}", json={})

    async def combination(self, lock_id: str) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request("GET", f"/locks/{lock_id}/combination")

    async def history(self, lock_id: str, payload: dict[str, Any] | None = None) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request("POST", f"/locks/{lock_id}/history", json=payload or {})

    async def settings(self, lock_id: str, payload: dict[str, Any]) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request("POST", f"/locks/{lock_id}/settings", json=payload)

    async def bondage_config(self, lock_id: str, payload: dict[str, Any]) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request("PATCH", f"/locks/{lock_id}/bondage-config", json=payload)

    async def permission_definitions(self) -> Any:
        return await self.request("GET", "/permissions/definitions")

    async def keyholder_notes(self, lock_id: str) -> Any:
        lock_id = self._path_segment(lock_id, "lock identifier")
        return await self.request("GET", f"/keyholder/notes/lock/{lock_id}")
