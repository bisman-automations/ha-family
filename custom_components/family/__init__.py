"""Family: chores and rewards for the family, with more family tools to come."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_MEMBER, ATTR_POINTS, ATTR_REASON, DOMAIN, SERVICE_ADD_POINTS
from .manager import FamilyError, FamilyManager, manager_of

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type FamilyConfigEntry = ConfigEntry[FamilyManager]

ADD_POINTS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEMBER): cv.string,
        vol.Required(ATTR_POINTS): vol.All(
            vol.Coerce(int), vol.Range(min=-10000, max=10000)
        ),
        vol.Optional(ATTR_REASON): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the dashboards' API and the actions once."""
    from .websocket import async_setup_websocket  # noqa: PLC0415

    async_setup_websocket(hass)

    async def add_points(call: ServiceCall) -> None:
        if (manager := manager_of(hass)) is None:
            raise FamilyError("Family isn't set up")
        await manager.async_handle_add_points(call)

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_POINTS, add_points, ADD_POINTS_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FamilyConfigEntry) -> bool:
    manager = FamilyManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    from .panel import async_register_panels  # noqa: PLC0415

    await async_register_panels(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FamilyConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
        from .panel import async_remove_panels  # noqa: PLC0415

        async_remove_panels(hass)
    return unloaded
