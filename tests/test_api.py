from __future__ import annotations

import pytest

from custom_components.chaster.api import ChasterApi, ChasterApiError


@pytest.mark.asyncio
async def test_request_rejects_non_api_paths() -> None:
    api = ChasterApi(None, "token")  # type: ignore[arg-type]
    with pytest.raises(ChasterApiError, match="single"):
        await api.request("GET", "//example")
    with pytest.raises(ChasterApiError, match="single"):
        await api.request("GET", "example")
