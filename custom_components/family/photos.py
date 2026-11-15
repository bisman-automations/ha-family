"""Photos a child takes when marking a chore done, for a parent to check.

The dashboard shrinks the picture and sends it as a JPEG data URL with
``family/complete``. It's kept as a file in ``<config>/family_photos`` named
after the chore's ledger entry, read back by parents with ``family/photo``,
and removed when its entry goes (undo) or after ``KEEP_DAYS``.
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import FamilyManager

FOLDER = "family_photos"
KEEP_DAYS = 14
MAX_BYTES = 2_000_000
PREFIX = "data:image/jpeg;base64,"


class Photos:
    """Chore photos on disk."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager

    @property
    def folder(self) -> Path:
        return Path(self.manager.hass.config.path(FOLDER))

    def _path(self, entry_id: str, keep: bool = False) -> Path:
        """A photo's file. ``keep``: kept for good (a chore's example)."""
        if not entry_id.isalnum():
            raise ValueError("That photo can't be found")
        return self.folder / f"{entry_id}{'.keep' if keep else ''}.jpg"

    @staticmethod
    def decode(data_url: str) -> bytes:
        """The JPEG in a data URL, checked."""
        if not isinstance(data_url, str) or not data_url.startswith(PREFIX):
            raise ValueError("The photo has to be a JPEG")
        try:
            data = base64.b64decode(data_url[len(PREFIX) :], validate=True)
        except binascii.Error as err:
            raise ValueError("The photo couldn't be read") from err
        if len(data) > MAX_BYTES:
            raise ValueError("The photo is too big")
        if not data.startswith(b"\xff\xd8"):
            raise ValueError("The photo has to be a JPEG")
        return data

    async def async_save(self, entry_id: str, data: bytes, keep: bool = False) -> None:
        path = self._path(entry_id, keep)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await self.manager.hass.async_add_executor_job(_write)

    async def async_read(self, entry_id: str, keep: bool = False) -> str | None:
        path = self._path(entry_id, keep)

        def _read() -> bytes | None:
            return path.read_bytes() if path.is_file() else None

        data = await self.manager.hass.async_add_executor_job(_read)
        return PREFIX + base64.b64encode(data).decode() if data else None

    async def async_delete(self, entry_id: str, keep: bool = False) -> None:
        path = self._path(entry_id, keep)
        await self.manager.hass.async_add_executor_job(
            lambda: path.unlink(missing_ok=True)
        )

    async def async_prune(self) -> None:
        """Remove photos older than ``KEEP_DAYS`` (not the ones kept)."""
        folder = self.folder
        oldest = time.time() - KEEP_DAYS * 86400

        def _prune() -> None:
            if not folder.is_dir():
                return
            for path in folder.glob("*.jpg"):
                if path.name.endswith(".keep.jpg"):
                    continue
                if path.stat().st_mtime < oldest:
                    path.unlink(missing_ok=True)

        await self.manager.hass.async_add_executor_job(_prune)
