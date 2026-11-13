"""A points sensor for each family member, for cards and automations."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FamilyConfigEntry, model
from .const import DOMAIN, NAME, SIGNAL_CHANGED
from .manager import FamilyManager

# Coordinator or push updates; nothing polls on its own.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FamilyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    manager = entry.runtime_data
    added: dict[str, MemberPointsSensor] = {}

    @callback
    def sync() -> None:
        """Add a sensor for each new member; remove those of deleted ones."""
        ids = {m["id"] for m in manager.members}
        new = [
            MemberPointsSensor(manager, entry.entry_id, m["id"])
            for m in manager.members
            if m["id"] not in added
        ]
        for sensor in new:
            added[sensor.member_id] = sensor
        if new:
            async_add_entities(new)
        registry = er.async_get(hass)
        for member_id in [m for m in added if m not in ids]:
            sensor = added.pop(member_id)
            if sensor.entity_id and registry.async_get(sensor.entity_id):
                registry.async_remove(sensor.entity_id)

    sync()
    entry.async_on_unload(manager.add_member_listener(sync))


class MemberPointsSensor(SensorEntity):
    """A member's points."""

    _attr_has_entity_name = True
    _attr_translation_key = "points"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "points"
    _attr_should_poll = False

    def __init__(self, manager: FamilyManager, entry_id: str, member_id: str) -> None:
        self.manager = manager
        self.member_id = member_id
        member = manager.member(member_id)
        self._attr_unique_id = f"{entry_id}_{member_id}_points"
        self._attr_translation_placeholders = {"member": member["name"]}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer=NAME,
            model="Chores and rewards",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_CHANGED, self.async_write_ha_state
            )
        )

    @property
    def available(self) -> bool:
        return any(m["id"] == self.member_id for m in self.manager.members)

    @property
    def native_value(self) -> int | None:
        return self.manager.points(self.member_id) if self.available else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.available:
            return {}
        member = self.manager.member(self.member_id)
        # Rewards this person can get, and who else each one is for
        # ("everyone", or the names). One they can't get is left out.
        rewards = [
            {
                "name": reward["name"],
                "points": int(reward.get("points") or 0),
                "eligible": self.manager.reward_eligible(reward),
            }
            for reward in self.manager.rewards
            if model.reward_for(reward, self.member_id)
        ]
        return {
            "member": member["name"],
            "chores_to_check": sum(
                1
                for e in self.manager.entries
                if e["member"] == self.member_id and e.get("review") == "pending"
            ),
            "rewards": rewards,
        }
