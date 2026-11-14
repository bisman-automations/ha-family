"""The shopping list from the meal plan.

Each day on the meal plan can list what it needs ("ingredients", one per
line or separated by commas). A parent picks a to-do list (remembered as
``settings.shopping_list``) and taps Add to the shopping list: everything
the coming days need goes on it with ``todo.add_item``, except what's
already on it and not ticked off (case ignored).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def needed(meals: dict[str, dict[str, str]], days: list[str]) -> list[str]:
    """What those days need, each thing once, in the order of the days."""
    text = "\n".join(meals.get(day, {}).get("ingredients", "") for day in days)
    return model.ingredient_list(text)


async def async_add_to_list(
    manager: FamilyManager, entity_id: str, days: list[str] | None = None
) -> dict[str, list[str]]:
    """Put the coming week's ingredients on a to-do list."""
    hass = manager.hass
    if not str(entity_id).startswith("todo.") or hass.states.get(entity_id) is None:
        raise _error("Pick a shopping list")
    today = dt_util.now().date()
    days = [d for d in days or model.week_days(today) if d >= today.isoformat()]
    wanted = needed(manager.meals, days)
    if not wanted:
        raise _error("No meals in the coming days list anything to buy")
    try:
        response = await hass.services.async_call(
            "todo",
            "get_items",
            {"status": ["needs_action"]},
            target={"entity_id": entity_id},
            blocking=True,
            return_response=True,
        )
    except HomeAssistantError as err:
        raise _error(f"Couldn't read the list: {err}") from err
    items = ((response or {}).get(entity_id) or {}).get("items") or []
    have = {str(i.get("summary", "")).casefold().strip() for i in items}
    added, skipped = [], []
    for name in wanted:
        if name.casefold() in have:
            skipped.append(name)
            continue
        try:
            await hass.services.async_call(
                "todo",
                "add_item",
                {"item": name},
                target={"entity_id": entity_id},
                blocking=True,
            )
        except HomeAssistantError as err:
            raise _error(f"Couldn't add {name}: {err}") from err
        added.append(name)
    if manager.settings.get("shopping_list") != entity_id:
        manager.settings["shopping_list"] = entity_id
        manager.save()
    return {"added": added, "skipped": skipped}
