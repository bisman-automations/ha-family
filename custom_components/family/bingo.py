"""Chore bingo: a 3×3 board of someone's chores for the week.

Each member gets nine of the dashboard chores they can do (picked the same
way all week, by week and member). A chore done this week marks its square.
A row, column or diagonal earns ``settings.bingo_line`` points, and the full
card ``settings.bingo_full``, given with the chore that finished it (so
undoing or rejecting that chore takes them back). With fewer than nine
chores to pick from, there's no board.
"""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from . import model

if TYPE_CHECKING:
    from .manager import FamilyManager

LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)
SIZE = 9
BONUS_LINE = "bingo_line"
BONUS_FULL = "bingo_full"


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def pick_board(chores: list[dict[str, Any]], member_id: str, day: date) -> list[str]:
    """Nine chore ids for the member's week (none with fewer than nine)."""
    seed = f"{week_start(day).isoformat()}:{member_id}:"
    usable = [
        c
        for c in chores
        if c.get("enabled", True)
        and not c.get("pool")
        and (not c.get("members") or member_id in c["members"])
    ]
    if len(usable) < SIZE:
        return []
    usable.sort(key=lambda c: hashlib.sha1((seed + c["id"]).encode()).hexdigest())
    return [c["id"] for c in usable[:SIZE]]


def lines_done(marked: list[bool]) -> int:
    return sum(1 for line in LINES if all(marked[i] for i in line))


class Bingo:
    """The week's boards and their bonuses."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager

    @property
    def points(self) -> tuple[int, int]:
        settings = self.manager.settings
        return int(settings.get("bingo_line") or 0), int(
            settings.get("bingo_full") or 0
        )

    def enabled(self) -> bool:
        return any(self.points)

    def board(self, member_id: str, day: date) -> list[str]:
        return pick_board(self.manager.chores, member_id, day)

    def marked(self, member_id: str, board: list[str], day: date) -> list[bool]:
        start = week_start(day).isoformat()
        done = {
            e["chore_id"]
            for e in self.manager.entries
            if e.get("kind") == model.KIND_CHORE
            and e["member"] == member_id
            and e.get("review") != model.REVIEW_REJECTED
            and e["at"][:10] >= start
        }
        return [chore_id in done for chore_id in board]

    def _given(self, member_id: str, kind: str, day: date) -> int:
        start = week_start(day).isoformat()
        return sum(
            1
            for e in self.manager.entries
            if e.get("kind") == model.KIND_BONUS
            and e.get("bonus") == kind
            and e["member"] == member_id
            and e.get("review") != model.REVIEW_REJECTED
            and e["at"][:10] >= start
        )

    def bonuses(
        self, member_id: str, entry: dict[str, Any]
    ) -> list[tuple[str, str, int]]:
        """Bonuses the chore just done earns on the board: (kind, title, points)."""
        line, full = self.points
        if not line and not full:
            return []
        day = dt_util.now().date()
        board = self.board(member_id, day)
        if entry.get("chore_id") not in board:
            return []
        marked = self.marked(member_id, board, day)
        found = []
        new_lines = lines_done(marked) - self._given(member_id, BONUS_LINE, day)
        if line:
            found.extend(
                (BONUS_LINE, "Bingo! A line on the board", line)
                for _ in range(max(0, new_lines))
            )
        if full and all(marked) and not self._given(member_id, BONUS_FULL, day):
            found.append((BONUS_FULL, "Bingo! The whole card", full))
        return found

    def snapshot(self) -> dict[str, Any]:
        """Each member's board for the Family dashboard (none when it's off)."""
        if not self.enabled():
            return {}
        day = dt_util.now().date()
        chores = {c["id"]: c for c in self.manager.chores}
        result = {}
        for member in self.manager.members:
            board = self.board(member["id"], day)
            if not board:
                continue
            marked = self.marked(member["id"], board, day)
            result[member["id"]] = {
                "cells": [
                    {
                        "chore_id": cid,
                        "name": chores[cid]["name"],
                        "emoji": chores[cid].get("emoji"),
                        "done": done,
                    }
                    for cid, done in zip(board, marked, strict=True)
                ],
                "lines": lines_done(marked),
                "full": all(marked),
                "line_points": self.points[0],
                "full_points": self.points[1],
            }
        return result
