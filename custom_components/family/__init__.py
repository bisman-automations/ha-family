"""Family: chores and rewards for the family, with more family tools to come."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_MEMBER,
    ATTR_POINTS,
    ATTR_REASON,
    DOMAIN,
    EVENT_NOTIFICATION_ACTION,
    SERVICE_ADD_POINTS,
    SUMMARY_HOUR,
)
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
    # Chores nobody checked count as done after a day or a week (a setting).
    entry.async_on_unload(
        async_track_time_interval(hass, manager.async_auto_check, timedelta(hours=1))
    )

    # Chores kept on a to-do list: their items open again when the chores come
    # back (just after midnight, and hourly in case a list was offline).
    @callback
    def _sync_todo(_now: Any = None) -> None:
        manager.todo_sync.schedule()

    entry.async_on_unload(
        async_track_time_change(hass, _sync_todo, hour=0, minute=0, second=5)
    )

    # The parents' Live Activity: a fresh one each day.
    @callback
    def _new_day(_now: Any = None) -> None:
        manager.live.new_day()

    entry.async_on_unload(
        async_track_time_change(hass, _new_day, hour=0, minute=0, second=10)
    )
    entry.async_on_unload(
        async_track_time_interval(hass, _sync_todo, timedelta(hours=1))
    )
    _sync_todo()
    # The weekly allowance (and old notes and meals cleared), checked hourly.
    entry.async_on_unload(
        async_track_time_interval(hass, manager.async_allowance, timedelta(hours=1))
    )
    # Today's calendar: every 15 minutes and just after midnight.
    entry.async_on_unload(
        async_track_time_interval(
            hass, manager.calendar.schedule, timedelta(minutes=15)
        )
    )
    entry.async_on_unload(
        async_track_time_change(
            hass, manager.calendar.schedule, hour=0, minute=0, second=10
        )
    )
    # Chores with set days, hours or turns: the dashboards follow them.
    entry.async_on_unload(async_track_time_change(hass, manager.async_tick, second=1))
    manager.async_tick()
    # Parents' phones: buttons on notifications, and the Sunday summary.
    entry.async_on_unload(
        hass.bus.async_listen(
            EVENT_NOTIFICATION_ACTION, manager.notices.async_on_action
        )
    )
    entry.async_on_unload(
        async_track_time_change(
            hass, manager.notices.weekly_tick, hour=SUMMARY_HOUR, minute=0, second=0
        )
    )
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
