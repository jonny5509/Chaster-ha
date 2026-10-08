from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chaster import config_flow
from custom_components.chaster.const import DOMAIN


async def test_user_flow_success(hass) -> None:
    with patch.object(
        config_flow.ChasterApi,
        "profile",
        new=AsyncMock(return_value={"username": "test"}),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "secret-token"}
        )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_TOKEN] == "secret-token"
    assert result["title"] == "Chaster"


async def test_user_flow_rejected_token(hass) -> None:
    from custom_components.chaster.api import ChasterApiError

    with patch.object(
        config_flow.ChasterApi,
        "profile",
        side_effect=ChasterApiError("bad token"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "secret-token"}
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TOKEN: "token"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"scan_interval": 120, "role_mode": "auto"},
    )
    assert result["type"] == "create_entry"
    assert entry.options["scan_interval"] == 120


async def test_reauth_flow(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TOKEN: "old-token"})
    entry.add_to_hass(hass)

    with patch.object(
        config_flow.ChasterApi,
        "profile",
        new=AsyncMock(return_value={"username": "test"}),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data={},
        )
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "new-token"},
        )

    assert result["type"] == "abort"
    assert entry.data[CONF_TOKEN] == "new-token"
