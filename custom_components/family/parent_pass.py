"""The parent PIN on the shared screen, and the short-lived passes it gives.

There's a family PIN that any admin sets, and each admin can also set their
own PIN (``settings.parent_pins``, by Home Assistant user id). An admin's own
PIN stops working if they stop being an admin, and the pass it gives says
which parent opened the controls. Both are set on the Family tab (admins
only). On a screen logged in as
someone who isn't an admin (the shared tablet), **Parents** asks for it.
The right PIN gives that login a pass: a random token the dashboard sends
with each parent command. A pass lasts ``PASS_SECONDS`` after its last use
and only works for the login it was given to. Passes live in memory, so a
restart ends them.

The PIN is stored as a salted PBKDF2 hash, never as itself. After
``MAX_TRIES`` wrong PINs in a row the pad is locked for ``LOCK_SECONDS`` and
the parents' phones are told.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .manager import FamilyManager

PIN_KEY = "parent_pin"  # the family PIN
PINS_KEY = "parent_pins"  # each admin's own PIN: {user id: hash}
PIN_MIN = 4
PIN_MAX = 8
ITERATIONS = 200_000
PASS_SECONDS = 5 * 60
MAX_TRIES = 5
LOCK_SECONDS = 5 * 60


def hash_pin(pin: str, salt: str | None = None) -> dict[str, Any]:
    """{salt, hash, iterations} for ``pin``."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), bytes.fromhex(salt), ITERATIONS
    )
    return {"salt": salt, "hash": digest.hex(), "iterations": ITERATIONS}


def pin_matches(pin: str, stored: dict[str, Any] | None) -> bool:
    if not stored or not stored.get("salt") or not stored.get("hash"):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode(),
        bytes.fromhex(stored["salt"]),
        int(stored.get("iterations") or ITERATIONS),
    )
    return hmac.compare_digest(digest.hex(), stored["hash"])


def _error(message: str) -> Exception:
    from .manager import FamilyError  # noqa: PLC0415 - manager imports this module

    return FamilyError(message)


def clean_pin(pin: str) -> str:
    pin = (pin or "").strip()
    if not pin.isdigit() or not PIN_MIN <= len(pin) <= PIN_MAX:
        raise _error(f"The PIN has to be {PIN_MIN} to {PIN_MAX} digits")
    return pin


@dataclass
class _Pass:
    user_id: str | None
    expires: float
    by: str | None = None  # the parent whose own PIN opened it


class ParentPasses:
    """Checks the PIN and keeps the passes it hands out."""

    def __init__(self, manager: FamilyManager) -> None:
        self.manager = manager
        self._passes: dict[str, _Pass] = {}
        self._wrong = 0
        self._locked_until = 0.0

    @property
    def _own(self) -> dict[str, dict[str, Any]]:
        return self.manager.settings.get(PINS_KEY) or {}

    @property
    def pin_set(self) -> bool:
        """Any PIN at all: the family's, or a parent's own."""
        settings = self.manager.settings
        return bool(settings.get(PIN_KEY) or settings.get(PINS_KEY))

    def status(self, user_id: str | None) -> dict[str, Any]:
        """For the PIN card: which PINs are set (never the PINs)."""
        return {
            "family": bool(self.manager.settings.get(PIN_KEY)),
            "mine": bool(user_id and user_id in self._own),
            "parents": sorted(
                str(h.get("name") or "A parent") for h in self._own.values()
            ),
        }

    def _taken(self, pin: str, skip: str | None) -> bool:
        """Another PIN (the family's, or another parent's) is these digits."""
        others = [] if skip == "" else [self.manager.settings.get(PIN_KEY)]
        others += [h for uid, h in self._own.items() if uid != skip]
        return any(pin_matches(pin, h) for h in others if h)

    def set_pin(
        self, pin: str | None, owner: str | None = None, owner_name: str | None = None
    ) -> None:
        """Set the family PIN (``owner`` None), or a parent's own (their user
        id). None or "" clears it. Ends every pass."""
        if pin:
            pin = clean_pin(pin)
            if self._taken(pin, "" if owner is None else owner):
                raise _error("That PIN is already used. Pick another one.")
            value = hash_pin(pin)
            if owner is None:
                self.manager.settings[PIN_KEY] = value
            else:
                self.manager.settings[PINS_KEY] = {
                    **self._own,
                    owner: {**value, "name": owner_name},
                }
        elif owner is None:
            self.manager.settings.pop(PIN_KEY, None)
        else:
            self.manager.settings[PINS_KEY] = {
                k: v for k, v in self._own.items() if k != owner
            }
        if not self.manager.settings.get(PINS_KEY):
            self.manager.settings.pop(PINS_KEY, None)
        self._passes.clear()
        self._wrong = 0
        self._locked_until = 0.0
        self.manager.changed()

    async def _match(self, pin: str) -> tuple[bool, str | None]:
        """(matched, the parent's user id for their own PIN)."""
        if pin_matches(pin, self.manager.settings.get(PIN_KEY)):
            return True, None
        for owner, stored in list(self._own.items()):
            if not pin_matches(pin, stored):
                continue
            user = await self.manager.hass.auth.async_get_user(owner)
            # Only while they're still an admin.
            if user is not None and user.is_active and user.is_admin:
                return True, owner
        return False, None

    async def unlock(self, pin: str, user_id: str | None) -> dict[str, Any]:
        """A pass for the right PIN. Raises FamilyError otherwise."""
        now = time.monotonic()
        if not self.pin_set:
            raise _error("No parent PIN is set. A parent sets one on the Family tab.")
        if now < self._locked_until:
            wait = int(self._locked_until - now) // 60 + 1
            raise _error(f"Too many wrong PINs. Try again in {wait} min.")
        matched, owner = await self._match((pin or "").strip())
        if not matched:
            self._wrong += 1
            if self._wrong >= MAX_TRIES:
                self._wrong = 0
                self._locked_until = now + LOCK_SECONDS
                self.manager.notices.pin_locked()
                raise _error(
                    f"Too many wrong PINs. Try again in {LOCK_SECONDS // 60} min."
                )
            raise _error("That's not the PIN. Try again.")
        self._wrong = 0
        self._prune(now)
        token = secrets.token_urlsafe(24)
        name = None
        if owner is not None:
            user = await self.manager.hass.auth.async_get_user(owner)
            name = user.name if user else self._own[owner].get("name")
        self._passes[token] = _Pass(user_id, now + PASS_SECONDS, name)
        return {"pass": token, "seconds": PASS_SECONDS, "by": name}

    def valid(self, token: str | None, user_id: str | None) -> bool:
        """True for a live pass given to this login; each use extends it."""
        if not token:
            return False
        now = time.monotonic()
        found = self._passes.get(token)
        if found is None or found.expires < now or found.user_id != user_id:
            if found is not None and found.expires < now:
                self._passes.pop(token, None)
            return False
        found.expires = now + PASS_SECONDS
        return True

    def lock(self, token: str | None) -> None:
        """End a pass (Back to Family, or the screen went idle)."""
        if token:
            self._passes.pop(token, None)

    def _prune(self, now: float) -> None:
        for token in [t for t, p in self._passes.items() if p.expires < now]:
            del self._passes[token]
