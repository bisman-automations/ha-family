"""Keep Family dashboard chores on a to-do list too.

A dashboard chore can name a to-do list (``todo_list``). While the chore can
be done, the list has an open item with the chore's name; once it's done the
item is ticked off, and when the chore comes back the item is opened again.

The items Family made are remembered in ``FamilyManager.todo_links``
(chore id -> list, item uid, whether it was left open, its name), so:

- an item is only changed when the chore changes (done, back, renamed,
  removed), never just because someone ticked or edited it on the list;
- an item that was deleted on the list is added again the next time the
  chore comes back;
- items Family made never count as chores from that list as well
  (``FamilyManager.linked_uids``);
- an item already on the list with the chore's name is used instead of
  adding another (``adopted``: it's left on the list when the chore stops
  using it), and its due date is kept (``due``) for a chore that shows
  only when due.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from .manager import FamilyManager

_LOGGER = logging.getLogger(__name__)

STATUS_OPEN = "needs_action"
STATUS_DONE = "completed"


class TodoSync:
    """Puts dashboard chores on their to-do lists, one change at a time."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self.hass = manager.hass
        self._lock = asyncio.Lock()
        self._again = False

    def schedule(self) -> None:
        """Sync soon. Calls while a sync runs are folded into one more pass."""
        if self._lock.locked():
            self._again = True
            return
        self.manager.entry.async_create_background_task(
            self.hass, self.async_sync(), "family todo sync"
        )

    async def async_sync(self) -> None:
        async with self._lock:
            while True:
                self._again = False
                await self._async_sync_once()
                if not self._again:
                    break

    async def _async_sync_once(self) -> None:
        manager = self.manager
        links: dict[str, dict[str, Any]] = manager.todo_links
        chores = {c["id"]: c for c in manager.chores}
        changed = False
        items_by_list: dict[str, dict[str, dict[str, Any]]] = {}

        # Chores that were removed, or moved to another list (or none).
        for chore_id, link in list(links.items()):
            chore = chores.get(chore_id)
            if chore is None or chore.get("todo_list") != link["list"]:
                await self._async_remove(link)
                del links[chore_id]
                changed = True

        for chore in manager.chores:
            target = chore.get("todo_list")
            if not target or not self._available(target):
                continue
            want_open = chore.get("enabled", True) and manager.chore_open(chore)
            link = links.get(chore["id"])
            if chore.get("due_only") or link is None:
                # Its item's due date can change on the list: read it again.
                if target not in items_by_list:
                    items_by_list[target] = await self._async_items(target)
                item = items_by_list[target].get((link or {}).get("uid", ""))
                if item is not None and (link or {}).get("due") != item.get("due"):
                    link["due"] = item.get("due")
                    changed = True
            if (
                link is not None
                and link["open"] == want_open
                and (link.get("name") == chore["name"])
            ):
                continue  # nothing changed for this chore
            if target not in items_by_list:
                items_by_list[target] = await self._async_items(target)
            items = items_by_list[target]
            if link is None or link["uid"] not in items:
                # Already on the list under the same name: use that item.
                taken = {
                    other["uid"] for other in links.values() if other["list"] == target
                }
                found = _same_name(items, chore["name"], taken)
                if found is not None:
                    link = links[chore["id"]] = {
                        "list": target,
                        "uid": found["uid"],
                        "open": found.get("status") != STATUS_DONE,
                        "name": found.get("summary"),
                        "adopted": True,
                        "due": found.get("due"),
                    }
                    changed = True
            if link is not None and link["uid"] in items:
                if await self._async_update(link, chore["name"], want_open):
                    link.update(open=want_open, name=chore["name"])
                    changed = True
                continue
            # Not on the list yet, or deleted there: add it when it's open.
            links.pop(chore["id"], None)
            if not want_open:
                continue
            uid = await self._async_add(target, chore["name"], set(items))
            if uid is not None:
                links[chore["id"]] = {
                    "list": target,
                    "uid": uid,
                    "open": True,
                    "name": chore["name"],
                }
                items[uid] = {"uid": uid, "summary": chore["name"]}
                changed = True
        if changed:
            manager.save()

    def _available(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in ("unavailable", "unknown")

    async def _async_items(self, entity_id: str) -> dict[str, dict[str, Any]]:
        """Every item on the list, open or ticked off, by uid."""
        try:
            response = await self.hass.services.async_call(
                "todo",
                "get_items",
                {"entity_id": entity_id, "status": [STATUS_OPEN, STATUS_DONE]},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Family: couldn't read %s: %s", entity_id, err)
            return {}
        items = (response or {}).get(entity_id, {}).get("items", [])
        return {i["uid"]: i for i in items if i.get("uid")}

    async def _async_add(
        self, entity_id: str, name: str, before: set[str]
    ) -> str | None:
        """Add an item and find its uid (todo.add_item doesn't return it)."""
        try:
            await self.hass.services.async_call(
                "todo",
                "add_item",
                {"entity_id": entity_id, "item": name},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Family: couldn't add %s to %s: %s", name, entity_id, err)
            return None
        after = await self._async_items(entity_id)
        new = [uid for uid, item in after.items() if uid not in before]
        same = [uid for uid in new if after[uid].get("summary") == name]
        return (same or new or [None])[-1]

    async def _async_update(
        self, link: dict[str, Any], name: str, want_open: bool
    ) -> bool:
        data: dict[str, Any] = {"entity_id": link["list"], "item": link["uid"]}
        if link.get("name") != name:
            data["rename"] = name
        if link["open"] != want_open:
            data["status"] = STATUS_OPEN if want_open else STATUS_DONE
        if len(data) == 2:
            return True
        try:
            await self.hass.services.async_call(
                "todo", "update_item", data, blocking=True
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Family: couldn't update %s: %s", link["list"], err)
            return False
        return True

    async def _async_remove(self, link: dict[str, Any]) -> None:
        # An item that was on the list before Family used it stays there.
        if link.get("adopted") or not self._available(link["list"]):
            return
        try:
            await self.hass.services.async_call(
                "todo",
                "remove_item",
                {"entity_id": link["list"], "item": [link["uid"]]},
                blocking=True,
            )
        except HomeAssistantError as err:
            # Already deleted on the list: nothing to do.
            _LOGGER.debug("Family: couldn't remove from %s: %s", link["list"], err)


def _same_name(
    items: dict[str, dict[str, Any]], name: str, taken: set[str]
) -> dict[str, Any] | None:
    """An item with this name (letter case and spaces aside) no other chore
    uses; an open one first."""
    key = " ".join(name.split()).casefold()
    matches = [
        i
        for uid, i in items.items()
        if uid not in taken
        and " ".join(str(i.get("summary", "")).split()).casefold() == key
    ]
    matches.sort(key=lambda i: i.get("status") == STATUS_DONE)
    return matches[0] if matches else None
