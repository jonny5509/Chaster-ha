from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from aiohttp import ClientError, ClientSession

from .const import API_BASE


class ChasterApiError(Exception):
    """Chaster API error with optional HTTP metadata."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _retry_after_seconds(value: str | None) -> int | None:
    """Parse Retry-After as either delta seconds or an HTTP date."""
    if not value:
        return None
    seconds = _header_int(value)
    if seconds is not None:
        return max(0, seconds)
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0, int((retry_at - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def _header_int(value: str | None) -> int | None:
    """Parse an integer-valued HTTP header without failing the request."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ChasterApi:
    """Small async client for the Chaster Public API."""

    def __init__(self, session: ClientSession, token: str) -> None:
        self._session = session
        self._token = token
        self.last_response_at: str | None = None
        self.last_error: str | None = None
        self.rate_limit: dict[str, int | None] = {
            "limit": None,
            "remaining": None,
            "reset": None,
        }
        self.rate_limited_until: float | None = None

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request using the developer token."""
        if not path.startswith("/"):
            raise ChasterApiError("Chaster API paths must start with '/'")

        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("Accept", "application/json")
        headers["Authorization"] = f"Bearer {self._token}"
        url = f"{API_BASE}{path}"

        try:
            async with self._session.request(method.upper(), url, headers=headers, **kwargs) as response:
                from datetime import datetime, timezone

                self.last_response_at = datetime.now(timezone.utc).isoformat()
                self.rate_limit = {
                    "limit": _header_int(response.headers.get("X-RateLimit-Limit")),
                    "remaining": _header_int(response.headers.get("X-RateLimit-Remaining")),
                    "reset": _header_int(response.headers.get("X-RateLimit-Reset")),
                }
                if response.status >= 400:
                    body = (await response.text())[:1000]
                    retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                    if response.status == 429:
                        # Do not blindly retry requests: some API calls mutate state.
                        # Instead, expose a cooldown so the coordinator can back off.
                        from time import time
                        reset = self.rate_limit.get("reset")
                        cooldown = retry_after
                        if cooldown is None and reset is not None:
                            cooldown = max(0, reset - int(time()))
                        self.rate_limited_until = time() + (cooldown if cooldown is not None else 60)
                    self.last_error = f"HTTP {response.status}"
                    raise ChasterApiError(
                        f"HTTP {response.status}: {body}",
                        status_code=response.status,
                        retry_after=retry_after,
                    )
                self.last_error = None
                if response.status == 204:
                    return None
                return await response.json(content_type=None)
        except ClientError as err:
            self.last_error = type(err).__name__
            raise ChasterApiError(str(err)) from err

    async def profile(self) -> Any:
        return await self.request("GET", "/auth/profile")

    async def locks(self, status: str | None = None) -> Any:
        params = {"status": status} if status else None
        return await self.request("GET", "/locks", params=params)

    async def lock(self, lock_id: str) -> Any:
        return await self.request("GET", f"/locks/{lock_id}")

    async def keyholder_locks(self, payload: dict[str, Any] | None = None) -> Any:
        """Fetch keyholder lock search pages when the API exposes pagination metadata.

        The endpoint's first response is returned unchanged when it does not
        advertise additional pages. Pagination is bounded to avoid exhausting
        the shared API request budget on very large accounts.
        """
        request_payload = dict(payload or {"status": "locked", "page": 0, "limit": 50})
        first = await self.request("POST", "/keyholder/locks/search", json=request_payload)
        if not isinstance(first, dict):
            return first

        collection_key = next(
            (key for key in ("items", "results", "locks", "data") if isinstance(first.get(key), list)),
            None,
        )
        if collection_key is None:
            return first

        meta = first.get("meta") if isinstance(first.get("meta"), dict) else {}
        total_pages = meta.get("totalPages", meta.get("total_pages", first.get("totalPages", first.get("total_pages"))))
        has_next = meta.get("hasNextPage", meta.get("has_next_page", first.get("hasNextPage", first.get("has_next_page"))))
        next_page = meta.get("nextPage", meta.get("next_page", first.get("nextPage", first.get("next_page"))))
        current_page = request_payload.get("page", 0)
        if not isinstance(current_page, int):
            current_page = 0
        try:
            total_pages = int(total_pages) if total_pages is not None else None
        except (TypeError, ValueError):
            total_pages = None

        combined = list(first[collection_key])
        # Ten pages (up to 500 records at the default limit) is a safety bound.
        for _ in range(9):
            if isinstance(next_page, int):
                page = next_page
            elif total_pages is not None:
                if current_page + 1 >= total_pages:
                    break
                page = current_page + 1
            elif has_next is True:
                page = current_page + 1
            else:
                break

            if page <= current_page:
                break
            page_payload = {**request_payload, "page": page}
            result = await self.request("POST", "/keyholder/locks/search", json=page_payload)
            if not isinstance(result, dict) or not isinstance(result.get(collection_key), list):
                break
            page_items = result[collection_key]
            if not page_items:
                break
            combined.extend(page_items)
            current_page = page
            page_meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
            total_pages = page_meta.get("totalPages", page_meta.get("total_pages", result.get("totalPages", result.get("total_pages", total_pages))))
            try:
                total_pages = int(total_pages) if total_pages is not None else None
            except (TypeError, ValueError):
                total_pages = None
            has_next = page_meta.get("hasNextPage", page_meta.get("has_next_page", result.get("hasNextPage", result.get("has_next_page"))))
            next_page = page_meta.get("nextPage", page_meta.get("next_page", result.get("nextPage", result.get("next_page"))))

        if len(combined) > len(first[collection_key]):
            first[collection_key] = combined
            first["_pagination_truncated"] = (
                (isinstance(total_pages, int) and current_page + 1 < total_pages)
                or has_next is True
                or isinstance(next_page, int)
            )
        return first

    async def lock_extension(self, lock_id: str, extension_id: str) -> Any:
        """Get information from an extension attached to a lock."""
        return await self.request(
            "GET", f"/locks/{lock_id}/extensions/{extension_id}"
        )

    async def lock_extension_action(
        self, lock_id: str, extension_id: str, payload: dict[str, Any]
    ) -> Any:
        """Trigger an action exposed by a lock extension."""
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
        return await self.request("GET", f"/conversations/{conversation_id}")

    async def send_message(self, conversation_id: str, payload: dict[str, Any]) -> Any:
        return await self.request("POST", f"/conversations/{conversation_id}", json=payload)

    async def create_conversation(self, payload: dict[str, Any]) -> Any:
        return await self.request("POST", "/conversations", json=payload)

    async def update_time(self, lock_id: str, seconds: int) -> Any:
        return await self.request(
            "POST", f"/locks/{lock_id}/update-time", json={"duration": seconds}
        )

    async def freeze(self, lock_id: str, frozen: bool) -> Any:
        return await self.request(
            "POST", f"/locks/{lock_id}/freeze", json={"isFrozen": frozen}
        )

    async def unlock(self, lock_id: str) -> Any:
        """Unlock a lock only after its timer has expired."""
        from datetime import datetime, timezone
        import time

        lock = await self.lock(lock_id)
        if not isinstance(lock, dict):
            raise ChasterApiError("Unable to verify lock timer before unlock")

        end_time = None
        for key in ("endDate", "endAt", "unlockDate", "unlockAt"):
            value = lock.get(key)
            if not value:
                continue
            if isinstance(value, (int, float)):
                end_time = float(value) / 1000 if float(value) > 10000000000 else float(value)
                break
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    end_time = parsed.timestamp()
                    break
                except ValueError:
                    continue

        if end_time is None:
            raise ChasterApiError("Lock has no valid end time; unlock is blocked")
        if time.time() < end_time:
            raise ChasterApiError("Lock timer has not expired; unlock is blocked")

        return await self.request("POST", f"/locks/{lock_id}/unlock")

    async def emergency_unlock(self, lock_id: str) -> Any:
        return await self.request("POST", f"/locks/{lock_id}/emergency-unlock", json={})

    async def archive(self, lock_id: str, keyholder: bool = False) -> Any:
        suffix = "/archive/keyholder" if keyholder else "/archive"
        return await self.request("POST", f"/locks/{lock_id}{suffix}", json={})

    async def combination(self, lock_id: str) -> Any:
        return await self.request("GET", f"/locks/{lock_id}/combination")

    async def history(self, lock_id: str, payload: dict[str, Any] | None = None) -> Any:
        return await self.request("POST", f"/locks/{lock_id}/history", json=payload or {})

    async def settings(self, lock_id: str, payload: dict[str, Any]) -> Any:
        return await self.request("POST", f"/locks/{lock_id}/settings", json=payload)

    async def bondage_config(self, lock_id: str, payload: dict[str, Any]) -> Any:
        return await self.request("PATCH", f"/locks/{lock_id}/bondage-config", json=payload)

    async def permission_definitions(self) -> Any:
        return await self.request("GET", "/permissions/definitions")

    async def keyholder_notes(self, lock_id: str) -> Any:
        return await self.request("GET", f"/keyholder/notes/lock/{lock_id}")
