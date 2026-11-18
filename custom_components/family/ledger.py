"""Quick lookups into the ledger, so a busy family's dashboard stays fast.

Pure (no Home Assistant imports). The ledger is one list of entries that
grows all year; reading every entry for every chore, member and goal made
each dashboard refresh walk it hundreds of times. ``Ledger`` groups the
same entry dicts by chore, member, day and kind once, and is rebuilt only
when the list itself changes: another list, a different length, or a
different first or last entry. Every way the ledger changes (add, remove,
drop old history) changes one of those. Adding entries at the end (a chore
done, a bonus) is the common case and is folded in without rebuilding
(2.16.0): the new entries are added to their groups, and to the time order
where their time puts them. A review that marks an entry
rejected or approved edits the entry in place, and these groups hold the
same dicts, so callers still see it; nothing here reads a review.

Callers pass a group to the same ``model`` helpers they used with the whole
list. Each helper still filters by chore, member, day or kind itself, so the
answer is the same, only quicker.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime
from typing import Any

_NONE: tuple[dict[str, Any], ...] = ()


def _fingerprint(entries: list[dict[str, Any]]) -> tuple[Any, ...]:
    if not entries:
        return (0,)
    first, last = entries[0], entries[-1]
    return (len(entries), id(first), id(last), first.get("id"), last.get("id"))


def _parse_at(entry: dict[str, Any]) -> datetime | None:
    """The entry's time, or None when it has none (or it can't be read)."""
    try:
        return datetime.fromisoformat(entry["at"])
    except KeyError, TypeError, ValueError:
        return None


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
        """These groups, brought up to date first when ``entries`` changed.

        Entries only added at the end of the same list are folded in
        (``_extend``); anything else (removed, replaced, another list) is a
        full rebuild. Either way ``version`` goes up.
        """
        fingerprint = _fingerprint(entries)
        if entries is self._source and fingerprint == self._print:
            return self
        if entries is self._source and self._appended_only(entries):
            self._extend(entries[self._print[0] :])
        else:
            self._build(entries)
        self._source = entries
        self._print = fingerprint
        self.version += 1
        return self

    def _appended_only(self, entries: list[dict[str, Any]]) -> bool:
        """Whether ``entries`` is what was grouped last time plus new ones at
        the end: longer, and the old first and last entries (the same dicts,
        with the same ids) are still first and where the end was.

        A removal anywhere before the old end shifts the old last entry down,
        so it's no longer at that index and the list is rebuilt.
        """
        old = self._print
        if len(old) != 5:  # nothing grouped yet (an empty list)
            return False
        count, first_id, last_id, first_key, last_key = old
        if len(entries) <= count:
            return False
        first, last = entries[0], entries[count - 1]
        return (
            id(first) == first_id
            and id(last) == last_id
            and first.get("id") == first_key
            and last.get("id") == last_key
        )

    def _extend(self, new: list[dict[str, Any]]) -> None:
        """Fold entries added at the end into the groups.

        Gives the same groups as ``_build`` of the whole list: every group
        keeps list order, and the time order sorts by (time, list position),
        so a new entry goes after every older-or-equal time already there
        (``bisect_right``); usually that's simply the end.
        """
        for entry in new:
            if (chore := entry.get("chore_id")) is not None:
                self._by_chore.setdefault(chore, []).append(entry)
            self._by_member.setdefault(entry.get("member"), []).append(entry)
            self._by_kind.setdefault(entry.get("kind"), []).append(entry)
            at = _parse_at(entry)
            if at is None:
                continue
            self._by_day.setdefault(at.date(), []).append(entry)
            _insert(self._times, self._in_time, at, entry)
            if chore is not None:
                _insert(
                    self._chore_times.setdefault(chore, []),
                    self._chore_in_time.setdefault(chore, []),
                    at,
                    entry,
                )

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
            if (at := _parse_at(entry)) is None:
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


def _insert(
    times: list[datetime],
    items: list[dict[str, Any]],
    at: datetime,
    entry: dict[str, Any],
) -> None:
    """Put ``entry`` in a time-ordered pair of lists, after equal times (it
    came later in the ledger), at the end when it's the newest."""
    if not times or times[-1] <= at:
        times.append(at)
        items.append(entry)
        return
    index = bisect_right(times, at)
    times.insert(index, at)
    items.insert(index, entry)
