"""Constants for Family."""

from __future__ import annotations

DOMAIN = "family"
NAME = "Family"

STORAGE_KEY = f"{DOMAIN}.data"
STORAGE_VERSION = 1

SIGNAL_CHANGED = f"{DOMAIN}_changed"

# Events, for automations.
EVENT_CHORE_DONE = "family_chore_done"
EVENT_CHORE_REVIEWED = "family_chore_reviewed"
EVENT_REWARD_REDEEMED = "family_reward_redeemed"

# Actions
SERVICE_ADD_POINTS = "add_points"
ATTR_MEMBER = "member"
ATTR_POINTS = "points"
ATTR_REASON = "reason"

# TV time rewards go through TV Mgmt's action.
TV_MGMT_DOMAIN = "tv_mgmt"
TV_MGMT_GRANT = "grant_extension"

# Ledger entries older than this are folded into each member's balance.
KEEP_HISTORY_DAYS = 400

MEMBER_COLORS = (
    "#E91E63",
    "#3F51B5",
    "#009688",
    "#FF9800",
    "#9C27B0",
    "#4CAF50",
    "#03A9F4",
    "#795548",
)
