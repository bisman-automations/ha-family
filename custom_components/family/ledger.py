"""Quick lookups into the ledger, so a busy family's dashboard stays fast.

Pure (no Home Assistant imports). The ledger is one list of entries that
grows all year; reading every entry for every chore, member and goal made
each dashboard refresh walk it hundreds of times. ``Ledger`` groups the
same entry dicts by chore, member, day and kind once, and is rebuilt only
when the list itself changes: another list, a different length, or a
different first or last entry. Every way the ledger changes (add, remove,
drop old history) changes one of those. A review that marks an entry
rejected or approved edits the entry in place, and these groups hold the
same dicts, so callers still see it; nothing here reads a review.

Callers pass a group to the same ``model`` helpers they used with the whole
list. Each helper still filters by chore, member, day or kind itself, so the
answer is the same, only quicker.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime
from typing import Any

_NONE: tuple[dict[str, Any], ...] = ()


def _fingerprint(entries: list[dict[str, Any]]) -> tuple[Any, ...]:
    if not entries:
        return (0,)
    first, last = entries[0], entries[-1]
    return (len(entries), id(first), id(last), first.get("id"), last.get("id"))


class Ledger:
    """Groups of one ledger list's entries; ask with ``current(entries)``."""

    def __init__(self) -> None:
        self._source: list[dict[str, Any]] | None = None
        self._print: tuple[Any, ...] = (-1,)
        self.version = 0
        self._by_chore: dict[str, list[dict[str, Any]]] = {}
        self._by_member: dict[str, list[dict[str, Any]]] = {}
        self._by_day: dict[date, list[dict[str, Any]]] = {}
        self._by_kind: dict[str, list[dict[str, Any]]] = {}
        self._times: list[datetime] = []
        self._in_time: list[dict[str, Any]] = []
        # Each chore's timed entries, oldest first, with their times.
        self._chore_times: dict[str, list[datetime]] = {}
        self._chore_in_time: dict[str, list[dict[str, Any]]] = {}

    def current(self, entries: list[dict[str, Any]]) -> Ledger:
        """These groups, rebuilt first when ``entries`` changed since."""
        fingerprint = _fingerprint(entries)
        if entries is not self._source or fingerprint != self._print:
            self._build(entries)
            self._source = entries
            self._print = fingerprint
            self.version += 1
        return self

    def _build(self, entries: list[dict[str, Any]]) -> None:
        by_chore: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        by_member: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        by_day: defaultdict[date, list[dict[str, Any]]] = defaultdict(list)
        by_kind: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        timed: list[tuple[datetime, int, dict[str, Any]]] = []
        for index, entry in enumerate(entries):
            if (chore := entry.get("chore_id")) is not None:
                by_chore[chore].append(entry)
            by_member[entry.get("member")].append(entry)
            by_kind[entry.get("kind")].append(entry)
            try:
                at = datetime.fromisoformat(entry["at"])
            except KeyError, TypeError, ValueError:
                continue
            by_day[at.date()].append(entry)
            timed.append((at, index, entry))
        timed.sort(key=lambda item: (item[0], item[1]))
        chore_times: defaultdict[str, list[datetime]] = defaultdict(list)
        chore_in_time: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for at, _index, entry in timed:
            if (chore := entry.get("chore_id")) is not None:
                chore_times[chore].append(at)
                chore_in_time[chore].append(entry)
        self._chore_times = dict(chore_times)
        self._chore_in_time = dict(chore_in_time)
        self._by_chore = dict(by_chore)
        self._by_member = dict(by_member)
        self._by_day = dict(by_day)
        self._by_kind = dict(by_kind)
        self._times = [item[0] for item in timed]
        self._in_time = [item[2] for item in timed]

    def chore(self, chore_id: str) -> list[dict[str, Any]] | tuple[()]:
        """Entries for one chore id (``routine:<id>``, ``pet:…`` included)."""
        return self._by_chore.get(chore_id, _NONE)  # type: ignore[return-value]

    def chore_since(
        self, chore_id: str, start: datetime | None
    ) -> list[dict[str, Any]] | tuple[()]:
        """One chore's entries at or after ``start`` (all of them for None)."""
        if start is None:
            return self.chore(chore_id)
        times = self._chore_times.get(chore_id)
        if not times:
            return _NONE  # type: ignore[return-value]
        return self._chore_in_time[chore_id][bisect_left(times, start) :]

    def member(self, member_id: str | None) -> list[dict[str, Any]] | tuple[()]:
        return self._by_member.get(member_id, _NONE)  # type: ignore[return-value]

    def day(self, day: date) -> list[dict[str, Any]] | tuple[()]:
        """Entries made on that (local) day."""
        return self._by_day.get(day, _NONE)  # type: ignore[return-value]

    def kind(self, kind: str) -> list[dict[str, Any]] | tuple[()]:
        return self._by_kind.get(kind, _NONE)  # type: ignore[return-value]

    def since(self, start: datetime) -> list[dict[str, Any]]:
        """Entries at or after ``start``, oldest first."""
        return self._in_time[bisect_left(self._times, start) :]

    def newest(self, count: int) -> list[dict[str, Any]]:
        """The ``count`` newest entries, newest first."""
        return self._in_time[: -count - 1 : -1] if count > 0 else []
