# Family: notes for Claude and other coding agents

Home Assistant custom integration (`family`), installed through the
Marketplace or HACS. Family tools for the household; the first is chores and
rewards. Kids mark chores done on a shared screen and get points straight
away, parents check them later, and points buy rewards (TV time through
[TV Mgmt](https://github.com/bisman-automations/ha-tv-mgmt), or anything a
parent hands out). More family tools will be added to this integration, so
keep new ones in their own modules and their own tabs. Read this before
changing anything.

## Layout

- `custom_components/family/`: the integration.
  - `__init__.py`: setup and unload; the `family.add_points` action is registered once in `async_setup`.
  - `config_flow.py`: set up once (`single_config_entry`); nothing to fill in. Everything else is edited on the Parents dashboard.
  - `model.py`: **pure (no Home Assistant imports)**: periods (daily, weekly, once), who has done a chore, balances, points in to-do item text. Tested in `tests/test_model.py`.
  - `manager.py`: `FamilyManager` (`entry.runtime_data`): members, chores, rewards, chore to-do lists and the ledger in one Store (`family.data`); completing, checking, redeeming, adjusting; reading and ticking off to-do items; events.
  - `websocket.py`: the dashboards' API (`family/*`). Everyone: `state`, `subscribe`, `complete`, `routine/step`, `redeem`, `undo`, `control`, `goal`, `note/add`, `note/remove`, `unlock`, `lock`. Parents (`_require_parent`: an admin, or a live parent pass sent as `pass`): `review`, `given`, `approve`, `adjust`, `save`, `delete`, `move`, `settings`, `meals`, `choices`. Admins only (`require_admin`): `pin`. Every command's schema takes an optional `pass`.
  - `parent_pass.py`: `ParentPasses` (`manager.passes`): the family PIN (`settings.parent_pin`) and each admin's own (`settings.parent_pins`: {user id: hash + `name`}; only while that user is an active admin; no two PINs the same digits), salted PBKDF2 hashes, never the PIN; `family/pin` with `own` sets yours, without it the family's; `status` (`pins` in an admin's snapshot) says which are set; `family/settings` replies leave the hashes out. The pass from someone's own PIN carries `by` (their name, shown on Back to Family) and the passes `family/unlock` hands out (random tokens in memory, tied to the login, `PASS_SECONDS` after last use; `family/lock` ends one; changing the PIN ends all). `MAX_TRIES` wrong PINs lock the pad for `LOCK_SECONDS` and send `notices.pin_locked`.
  - `panel.py` + `frontend/family-panel.js`: one plain web component (no build step). The sidebar has one panel, **Family** (`/family`, everyone). The page has two views, `family` and `parents` (`_view`, `_mode`): **Parents** in the toolbar (or at the top of the card) switches straight away for an admin (`is_admin`) and asks for the PIN otherwise (`pin_set`; the snapshot's `parent` says whether the parent data came back); **Back to Family**, or `IDLE_MS` without a tap, ends the pass. `_ws` adds `pass` to `family/*` messages. `/family-parents` (the Parents sidebar panel before 2.0.0, where notifications link) is still registered, hidden from the sidebar and open to every login, with `config.mode = "parents"`: it starts in the parent view (PIN pad for non-admins). `lovelace/*` calls (Make a Family dashboard, `_followMembers`) are made only for admins. Registered only when the frontend is loaded.
  - `trades.py`: `Trades` (`manager.trades`, collection `trades` in the Store, today's only): `offer` (one of your own dashboard chores today, not up for grabs, to one person or anyone), `take` (not your own, not one you already have; notifies parents with `notices.trade_to_approve`), `cancel` (before a yes), `decide` (parent). An approved trade swaps `from` for `to` in that chore's members for the day in `manager._effective` (`trades.apply`, after turns; the chore gets `traded`). Websocket `trade/offer`, `trade/take`, `trade/cancel` (everyone), `trade/decide` (parents).
  - `voice.py`: `Voice` (`manager.voice`): Assist sentences as conversation triggers (`async_validate_trigger_config` + `async_initialize_triggers`, the same as an automation's conversation trigger; the action returns a `ScriptRunResult` with the reply). Only when `conversation` is loaded (`after_dependencies`). "I" is `member_for_user` of the speaker's user; `find_member` / `find_chore` match names. Completing goes through `async_complete`. Tests need conversation's requirements (`core-requirements: conversation` in `test.yml`).
  - `parents_notify.py`: `ParentNotices` (`manager.notices`): the parents' phone notifications, their buttons and the weekly summary.
  - `routines.py`: `Routines` (`manager.routines`): routines (`routines` in the Store) and today's ticked steps (`routine_steps`, {day, steps: {routine id: {member id: [step numbers]}}}, reset each day).
  - `live_activity.py`: `ChoreActivity` (`manager.live`): the parents' Live Activity of each child's own chores today.
  - `calendar_today.py`: `CalendarToday` (`manager.calendar`): today's events from the picked calendars.
  - `sensor.py`: a points sensor per member, added and removed as members change.
  - The same script also defines `family-card` (the Family dashboard as a Lovelace card, no toolbar), loaded on every dashboard with `frontend.add_extra_js_url`: a login's default dashboard has to be a Lovelace dashboard, not a panel. The Parents dashboard's **Make a Family dashboard** sends `lovelace/dashboards/create` (`family-dashboard`, hidden from the sidebar) and `lovelace/config/save` (one panel view with the card); `test_family_dashboard_messages` checks those messages against Home Assistant. `familyViews` gives it a **Home** tab (path `family`) and one tab per member (`family-member-<id>`, a card with `member: <id>`); existing tabs keep their cards and only their title follows, and tabs with other paths are kept after them. Saving or removing a member updates the dashboard when it exists (`_followMembers`); the button reads **Update the Family dashboard** then. A card with `member` shows only that person (`_pinned`), and the idle reset goes back to them.
- `scripts/panel-preview/index.html`: fakes Home Assistant with a sample family to look at both dashboards (`?mode=family|parents`, `&theme=dark`). Its fake backend must answer like the real one.
- `tests/`: pytest.

## Checks

The shared checks below. There are no Node tests and no mypy. For dashboard
changes, run `node --check` on the script and look at the preview page in a
browser (Playwright is available) at a landscape display size (1280x800), at
phone width (390px), and in the dark theme.

## Conventions

- **Points are given straight away.** Completing a chore adds a ledger entry with `review: pending`. A parent approves it or marks it rejected (didn't happen); rejected entries don't count toward a balance and free the chore again. A to-do chore is ticked off its list when done and put back when rejected.
- **Balances come from the ledger** (`model.balance`) plus `carried`: entries older than `KEEP_HISTORY_DAYS` are folded into `carried` when loading.
- **Chore availability:** dashboard chores repeat daily, weekly (from Monday) or once. With no members picked, anyone can do it and it's done once per period; with members picked, each of them can do it once per period. To-do chores are available while the item is open; the list decides (`FamilyManager._done`).
- **Repeats** (`model.REPEATS`): `daily`, `weekly`, `once`, and ones that come back once done: `after_days` (`repeat_days` days after the day it was done), `always` (never done), `after_check` (done only while still to check). `model.done_by` decides.
- **Dashboard chores on a to-do list** (`todo_sync.py`, a chore's `todo_list`): `TodoSync` adds an item while the chore is open (`chore_open`), ticks it when done, reopens it when it comes back, renames and removes it. Links are in `todo_links` (Store); items change only when the chore's state changes, and `linked_uids` keeps them out of that list's to-do chores. It runs after every `_changed`, at midnight and hourly; it saves with `save()`, never `_changed`, so it doesn't loop.
- **To-do item points:** a list's `item_points` (set per item on the Parents dashboard, keyed by `model.item_key(name)` so a repeating item keeps them) win; then `model.todo_points` reads `[5]`, `(5 points)` or `- 5 pts` at the end of an item; otherwise the list's points (`model.todo_item_points`). Saving a list merges `item_points`: `None` removes one, items not open now keep theirs. `item_members` (by `item_key`, merged the same way; an empty list removes one) gives single items their own people; `manager._item_members` falls back to the list's `members`, and the item's up-for-grabs uses its own people. A list's `due_only` keeps items out of `all_chores` until `model.todo_due` (the item's `due`, a date or a local time, `_local_due`); items with no due date always show, and `async_tick` runs while any list has it, so items appear when their time comes.
- **TV time** calls `tv_mgmt.grant_extension` with `profile_id` (the TV's config entry), `minutes`, `whole_home` and `reason` ("Alex's reward: …") before the points are taken, so a failure costs nothing. TV Mgmt before 1.21.0 has no `reason`: on `vol.Invalid` it's called again without it. The minutes are extra time for today on that TV, and for today on the whole home when `whole_home` is set. TV Mgmt 1.21.1 counts every grant from this week toward the weekly whole-home limit itself, and resets today's per-TV and daily whole-home extension at midnight. It has no day, week, or carry-over field; a field it doesn't know is rejected, so Family does not send one. Unused minutes the next day are TV Mgmt's to keep available. The reward entry keeps `tv`, `minutes`, `whole_home` so an undo can take the time back.
- **Undo** (`family/undo`, open to everyone): `model.can_undo`, within `UNDO_SECONDS` of the tap, for a chore still to check or a reward not handed out (TV time is taken back with negative minutes). The entry is removed, not marked.
- **Reward limits:** a reward's `limit` (`daily`/`weekly`, per person, `model.reward_used_by`); the snapshot sends `used_by`.
- **Who can get a reward** (`members`): `None` is everyone (the default, what storage version 2 writes for a reward saved before it, and what a save stores when every current member is selected, so people added later are included). A list of member ids is only those people. An empty list means nobody: the reward is unavailable. The Parents editor is one dropdown of the family, with no Everyone checkbox and no Everyone or All row. A new reward and a reward stored as everyone start with every person ticked. Ticking nobody warns that nobody can get it. A list that already names every member is not rewritten on load; saving it again stores `None`. Removing a member drops them from every list; if that empties a list it stays empty, it does not become everyone. `model.reward_selection` is the save rule; `model.reward_for` decides redeeming and saving up; `model.reward_visible` decides the Family dashboard and card (someone's page shows theirs and everyone's, everyone's page shows only rewards for everyone). `async_redeem` (alone or together) and `set_goal` refuse anyone else. The points sensor's `rewards` attribute and `family_reward_redeemed`'s `eligible` say who it's for (`everyone`, or the names). Chores, to-do lists and home controls are a different control: a tick per person, and none ticked means anyone. They have no Everyone checkbox. Notes and calendars pick one person or the whole family in a single choice. Those stay as they are.
- **Auto-check:** `settings.auto_check` (`day`/`week`, admin `family/settings`). `async_auto_check` runs on load, on saving the setting and hourly; entries get `auto: true` and `family_chore_reviewed` has `automatic: true`.
- **The shared screen isn't an admin.** Anything that changes the setup, checks chores or changes points by hand must be `_require_parent` (an admin, or the parent PIN's pass). Changing the PIN is `require_admin`. Completing chores, redeeming rewards and using home controls are open to everyone on purpose.
- **Home controls** (`controls` in the Store): entities a parent puts on the Family dashboard. `model.control_kind` decides what a tap does (toggle, run, open, lock, media, or view only) and `model.control_service` maps an action to a service; anything else is refused. `family/control` only runs controls in the list, with the caller's context. The dashboard reads live state from `hass.states` and redraws just the Home tiles when one changes.
- **Set days and hours** (`days`, Monday 0; `from_time` / `until_time`, "HH:MM", may cross midnight): `model.available` decides what `chores_for` shows and `async_complete` allows; `model.on_day` (the day only) decides `chore_open` (to-do items) and the all-done bonus, so a bedtime chore still to do keeps it from firing. `manager.async_tick` runs every minute and tells the dashboards when the visible chores (or whose turn) change; it does nothing when no chore has days, hours or turns.
- **Own chores and up for grabs** (`model.is_grab`, `model.is_own`): a chore (or to-do list, `grab`) with nobody picked is always up for grabs; with people picked it is when `grab` is set; one taken in turns never is. Up for grabs is done once by whoever's first (`"*"` in `done_by`), only by its people. Own chores are what `_own_today` counts for the all-done bonus and the snapshot's `own_today` ({total, left, done, missed}); `_own_left` treats a chore the member did today as done for the day even when it came back (`after_check`, `always`), and `missed` counts ones left whose hours are over (`model.hours_over`), shown as "missed" instead of "to do". The all-done bonus entry is written even with 0 points: it marks the day for streaks (feeds and toasts hide 0-point bonuses). `model.streak`: days with an all-done bonus not rejected; a day with none of their own dashboard chores (`_has_own`, turns not counted) is a day off; before `settings.streak_rule_from` (set on first load of 1.10.0) any chore counted, the old rule. A streak bonus is only earned by finishing the day. The Parents **Chores** tab starts with **Who does what** (`_choreMatrix`): chores (and to-do lists) by kind against each member. The Family page: **Going for** (`_goingFor`), **My chores** and **Up for grabs** on someone's page, only **Up for grabs** for everyone (nobody picked) on everyone's; the people strip shows `_todoLine`.
- **Checking off** (panel `ds.chore`, only on a chore tile's round `.check` button; the tile itself is a `div` and does nothing): on someone's page, or for a chore only one person can do (`can` of one), a tap completes it straight away (`quick` sheet, nothing shown; the toast can undo); otherwise the who-did-it sheet. An `all_done` bonus in the reply plays `_celebrate`. The people strip shows `_todoLine` as a ✓ done/total pill (and missed).
- **Parents' chores** (`_is_parent`): a member whose person's Home Assistant user is an admin gets `review: approved` (`parent: true`) straight away and no parent notification.
- **Turns** (`turns`, `turn_every` `time`/`day`/`week`, `turn_first`, `turn_from`): `model.turn_member`. Saving a chore anchors the turn (`turn_first` from now). `manager._effective` makes a turn chore look like a chore for one person (`members: [turn]`, `turn`, `rotation`); a turn chore is done once per period (`*`), like a chore for anyone. A chore that didn't happen doesn't move the turn on.
- **Rewards together** (`family/redeem` with `together`, open to everyone): `manager._redeem_together` splits the cost with `model.split_points` (as evenly as balances allow; each must put in something) and adds one reward entry per member with `given: to_approve`, a shared `group`, `together` (the ids) and `total`. The points are held: they count in balances and reward limits. `family/approve` (admin, `group_id`, `approved`) or the phone's `FAMILY_YES_`/`FAMILY_NO_` buttons: yes gives TV or music time once (kept on the first share) or makes the group `to_give`; no removes the group. Undo and **Handed out** act on the whole group; undo only while it waits. The snapshot sends `to_approve` (one per group, with `shares`) and `to_give` lists a group once. `splitPoints` in the panel mirrors `split_points` for the sheet's preview.
- **Section order** (`settings.section_order`, `model.SECTIONS` / `model.section_order`: known keys once each, missing ones appended): set on the Parents **Family** tab, sent to everyone as the snapshot's top-level `section_order`, and the Family dashboard draws its sections in that order.
- **Parents cards fold:** every `.card > h2` gets `data-fold` (`_foldCards`, its title minus a trailing count); folded keys are kept per device in `localStorage` (`family-parents-closed`), with an in-memory copy (`_closedCards`), and a folded card stays folded through every redraw. A button in a folded card's heading opens it.
- **One tile per chore:** `all_chores` lists dashboard chores first, then each to-do item once: an item whose `item_key` matches a switched-on dashboard chore or an item already listed is left out. A dashboard chore with a `todo_list` gets `on_list` (the list's name), shown like a to-do chore's `list` (`list` itself still means a to-do chore).
- **Hide empty sections:** `settings.hide_empty_sections`, sent to everyone as the snapshot's top-level `hide_empty_sections`; the Family dashboard then leaves out My chores, Up for grabs, Today, Rewards and Lately when they're empty. Notes always shows (it holds Add a note).
- **Item emojis:** a to-do list's `item_emojis` (by `item_key`, merged like `item_points`; empty removes one) give single items an `emoji`.
- **Quick points:** `settings.quick_points` ([{label, emoji, points}], `model.quick_points`: blank labels and 0 points dropped, at most `MAX_QUICK_POINTS`, points may be negative), admin only (in the admin `settings` snapshot). The **Quick points** card on To check calls `family/adjust` with the button's label as the reason, so a tap is an ordinary points change.
- **Leaving items out:** a to-do list's `item_skip` (a list of `item_key`s; the save takes `{name: bool}` and merges, so items not open now keep theirs) keeps those items out of `all_chores`. The item rows send `skip`; the panel shows skipped items in a folded **Left out** group.
- **Reusing to-do items:** before adding a dashboard chore's item, `TodoSync` looks for an item with the same name (case and spaces ignored, open first) no other chore uses, links it with `adopted: true`, and never deletes an adopted item. A chore's `due_only` (only with a `todo_list`) hides it in `all_chores` until its linked item's `due` (`link["due"]`, refreshed by the sync) is today or past.
- **Family goal:** `settings.family_goal` ({name, emoji, target, since, reached_at}), set by admin `family/settings` (`family_goal`, or None to remove; `restart_goal` counts from now). `model.goal_progress` adds chore and bonus points not rejected since `since` (nothing is spent). `manager._check_goal` (in every `_changed`) sets `reached_at` once and fires `family_goal_reached`. The snapshot sends top-level `family_goal` to everyone; the Family dashboard shows it first under **Going for** on every page; the Parents card is at the top of **Rewards**.
- **Speaker reminders** (`reminders.py`, `manager.reminders`): a dashboard chore's `remind_time` ("HH:MM") and `remind_speakers` (media players only) with `settings.reminder_tts` (a `tts.` entity, picked on the Family tab). `async_tick` calls `reminders.check` every minute while any chore has one; `manager.still_to_do` (ignores hours) decides who's named, and nothing is said once it's done. Said once a day (`_said`), with `tts.speak` in a background task; failures are logged. `family/choices` sends `voices` and `players`.
- **Routines** (`routines.py`, collection `routines`, Parents **Routines** tab): {name, emoji, points, members (none: everyone), steps (1 to `MAX_STEPS`), days, from_time, until_time, enabled}; `model.available` decides when it shows. `family/routine/step` (open to everyone: `routine_id`, `member_id`, `step`, `done`) ticks a step; ticking the last one finishes it with a chore-like ledger entry (`kind: chore`, `routine_id`, `chore_id: "routine:<id>"` so no chore counts it, review pending, parents approved straight away, `family_chore_done` with `routine: true`). Finished today = such an entry today not rejected; a finished routine can't be ticked again that day. Routines don't count toward own chores, the all-done bonus or streaks. The snapshot sends `routines` (today's, with `who`, `ticked`, `finished`) to everyone and `all_routines` to admins. Family dashboard section `routines` (`_routineTile`, `_routineSheet`): someone's page shows theirs; everyone's shows all and asks who.
- **Saving up:** a member's `goal` (a reward id), set by `family/goal` (open to everyone, like redeeming), kept by `save_member`, cleared when that reward is redeemed or deleted.
- **Music time** rewards (`music_time`, `speaker`, `minutes`, `whole_home`) call `media_mgmt.grant_extension` like TV time (with `reason`, and `whole_home` only when true; on `vol.Invalid`, for Media Mgmt before 1.5.0, again with neither); undo takes it back, the whole home's time too.
- **Parents' phones** (`parents_notify.py`, not `notify.py`: that name is a platform): settings `notify_targets`, `notify_done`, `notify_rewards`, `weekly_summary`. Notifications are sent in background tasks, tagged `family-<entry id>`, and cleared when the entry is checked, handed out, undone or auto-checked. Buttons come back as `mobile_app_notification_action` (`FAMILY_RIGHT_`, `FAMILY_DIDNT_`, `FAMILY_GIVEN_` + entry id) and are acted on only when the event's context user is an admin. The summary is sent Sunday at 18:00 (`SUMMARY_WEEKDAY`, `SUMMARY_HOUR`). Tests that move the clock use dates ahead of now (`_next`): time listeners only fire forwards.
- **Live Activities** (`live_activity.py`): `settings.live_activity` (one for the family, tag `family-chores-<entry id>`) and `settings.live_per_child` (one per child, tag `…-<member id>`; "All done!" then cleared after `DONE_SECONDS`, kept in `_shown` so it isn't shown again that day), either or both, to the parents' phones (`notices.targets()`) with `live_update`, `progress`/`progress_max` and `critical_text`. `settings.live_from` ("HH:MM") holds them until then (`tick`, from `async_tick` every minute). Rows are members with own chores today (`own_today`) who aren't parents (`is_parent`). Pushed from `_changed` and when `async_tick` sees the visible chores change, only when what each shows changes (`_shown`); cleared when no longer wanted and at 00:00:10 (`new_day`).
- **History filter** (Parents **History**, panel only): **Who** (a member) and **Search** (every word in the entry's title). `_historyList` redraws just the list while typing, and `_render` does the same when a live update comes in during typing.
- **Websocket fields:** never name a field `id`; it's the message's own id (`delete` uses `item_id`).
- **Dashboard:** escape everything with `esc()`; use Home Assistant's theme variables; big touch targets on the Family dashboard.
- **Bonuses and penalties** are ledger entries (`kind` `bonus` / `penalty`) with `for_entry`, the chore entry they belong to. Undo removes them with the chore; **Didn't happen** marks bonuses rejected and adds a penalty (`model.penalty_points`: the parent's number, else the chore's or list's `penalty` stored on the chore entry, else `settings.penalty`); **Done right** after that restores bonuses and removes the penalty. All-done counts only chores with the member picked; streaks are days with a chore not rejected (`model.streak`). `family/settings` changes only the keys sent.
- **Shared screen:** the Family dashboard goes back to `me` (or everyone) after `IDLE_MS` without a tap; tiles on someone's own page hide their own name/picture.
- **Family dashboard sections** (`_section`, `_fit`): each `[data-fit]` box shows its first row (the grid's column count, read from `gridTemplateColumns`; 3 for Lately), all, or is closed; the choice is per screen in `localStorage` (`family-sections`). `_fit` runs after every render, after Home tiles redraw, and on resize.
- **Notes** (`notes` in the Store): `family/note/add` and `family/note/remove` are open to everyone; a note added by an admin has `parent: true` and only an admin can remove it. Notes with `until` (a date) go after that day (`model.note_current`, pruned hourly). At most `MAX_NOTES` showing.
- **Meals** (`meals` in the Store: ISO date -> breakfast/lunch/dinner): `family/meals` is admin only; days older than `KEEP_MEAL_DAYS` are dropped. The snapshot sends the next 7 days.
- **Today's calendar** (`calendar_today.py`, `settings.calendars` = [{entity_id, member}]): today and the next days (`DAYS`, 7) read with `calendar.get_events` on load, every 15 minutes, after midnight and when a picked calendar's state changes. Not stored. Each event has `days` (`model.event_days`: the days it covers in the window). The snapshot sends `today`, `upcoming` ([{date, events}], for the Today section's **Next few days** pop-up) and `has_calendars` (the section shows, with "Nothing today", whenever calendars are picked). Timed events already over are faded with an **Over** tag (`eventOver`); the idle timer redraws when that count changes.
- **Allowance:** a member's `allowance` (points a week), given by `async_allowance` (hourly) once per ISO week (`settings.allowance_week`) at `allowance_day`/`allowance_hour` (`model.allowance_due`); a missed week isn't made up. Entries have `kind: allowance`. `settings.point_value` and `currency` make the snapshot's `money`.
- **Badges** (`model.BADGES`, `model.badges_earned`): earned from the ledger and the streak, stored on the member (`badges`: {key: date}) so they outlive the history; `save_member` keeps them. `manager._check_badges` runs in every `_changed` (quietly once on load, so an update doesn't celebrate old history), fires `family_badge_earned` and queues `new_badges`; `complete`, `redeem` and `cash_out` replies carry the member's new ones (`take_new_badges`) for the panel's toast. The snapshot sends each member's `badges` (`model.badge_list`).
- **Cash out** (`manager.cash_out`, websocket `cash_out`, open to everyone): needs `settings.point_value`; a ledger entry `kind: cashout` with `money`, `given: to_give`, points taken now (`model.cashout_points`: 1 to the balance). It's in `to_give`; **Paid** is `family/given`; `cash_out/cancel` (parents) removes it.
- **Week by week** (`model.weekly_stats`, snapshot `weeks` for parents): the last 8 ISO weeks per member: `earned` (positive entries), `spent` (rewards and cash outs), `chores` (chore entries); rejected ones don't count. Shown at the top of History (`_weeksCard`).
- **No personal details in the repo**: sample families use made-up names.

## Open decisions

- None.

<!-- BEGIN bisman-automations shared rules -->
<!-- This block is the same in every bisman-automations repo. Edit it in
     bisman-automations/.github (templates/CLAUDE.shared.md) and copy it to
     every repo; the Validate workflow's "standards" job checks it matches. -->

## Shared rules (every bisman-automations repo)

### Releases

- The version lives in `custom_components/<domain>/manifest.json`. Anything
  else that repeats it is called out in the repo-specific notes below and is
  bumped in the same commit.
- Versions follow [Semantic Versioning](https://semver.org): patch for fixes,
  translations, docs and CI; minor for new features, options or entities;
  major when something users rely on is removed or renamed (entities,
  services, events, options) or setup has to be redone.
- Check what is released before choosing a version:
  `git ls-remote --tags origin | awk -F/ '{print $3}' | sort -V | tail -1`
  (`sort -V`: plain sorting puts `v1.10.0` before `v1.9.0`). Never add
  changes to a released version. If the manifest version has no tag yet,
  add to its CHANGELOG section instead of bumping again.
- Every push to `main` ships as a release. In that same commit, named
  `Release X.Y.Z`, bump the manifest version and write the notes directly
  under a new `## [X.Y.Z] - YYYY-MM-DD` heading in `CHANGELOG.md` (Keep a
  Changelog: Added, Changed, Deprecated, Removed, Fixed, Security), with
  that version's compare link at the bottom. There is no `## [Unreleased]`
  section and no `[Unreleased]:` compare link. New work is not collected
  under a holding heading and moved later; the release commit is where the
  heading and the entries are written. The standards check fails if a
  `## [Unreleased]` heading is present.
- Ask Donavan before every push. Push fast-forward only: never force-push,
  rebase or amend anything already pushed, or rewrite history in any other
  way. Rewriting history orphans the release tags (it broke drafting in
  ha-button-actions).
- Pushing to `main` runs **Draft release**, which creates or refreshes a
  draft `vX.Y.Z` with that version's CHANGELOG section as the notes, the
  commits since the last release and `<domain>.zip`. **Donavan publishes
  the draft himself**, and publishing creates the tag. Never create or push
  tags, publish releases, or edit published releases.
- Publishing runs **Release check**: the tag must match the manifest version
  and the CHANGELOG, and be on `main`. If it fails, fix it with a new patch
  release, not by moving the tag.

### Commits

- Author commits as `Donavan Becker <donavan.becker@icloud.com>` (set
  `git config user.name` / `user.email` in the clone). HACS's
  default-repository check needs the submitter to have a fair share of the
  commits. Credit an AI assistant with a `Co-Authored-By:` trailer if you
  like, never as the author.
- Subject lines are plain, imperative and say what changed for the user
  ("Show Pico remotes as unavailable when Lutron isn't running"). No
  `fix:`/`feat:` prefixes. Release commits are "Release X.Y.Z".
- Commit and push only when asked.

### CI (shared workflows)

- `.github/workflows/` holds four thin callers of the reusable workflows in
  [bisman-automations/.github](https://github.com/bisman-automations/.github):
  `test.yml` (lint, frontend, pytest on the oldest supported and the newest
  Home Assistant, plus the upcoming one as information only), `validate.yml`
  (hassfest, HACS, standards), `draft-release.yml` and `release-check.yml`.
  Don't add jobs to the callers. Use the shared workflow's inputs, or change
  the shared workflow so every repo gets the improvement.
- `requirements_test.txt` leaves `pytest-homeassistant-custom-component`
  unpinned (newest Home Assistant) and pins ruff (and mypy where used).
  `requirements_test_min.txt` pins the harness release for the minimum in
  `hacs.json`: the newest harness release of that month. CI fails if they
  drift apart.
- Raising the minimum Home Assistant means changing, together: `hacs.json`,
  `requirements_test_min.txt`, `python-min` in `test.yml` (3.13 up to
  2026.2, 3.14 from 2026.3), the README's Home Assistant badge, and a
  CHANGELOG entry.
- Home Assistant 2026.3 and newer need Python 3.14 (3.14.2+).
- The published hassfest rejects `categories` in `manifest.json` and Pillow
  in `requirements`. Leave both out.
- Dependabot (`.github/dependabot.yml`) proposes action and pinned-tool
  updates weekly. It ignores the test harness on purpose.
- Test and Validate also run every Thursday, the day after Home Assistant's
  betas come out. The **next** test job (newest pre-release harness) is
  information only: when it fails, fix the cause before that release ships.

### Before saying work is done

Run from the repo root, in a Python 3.14 venv with `requirements_test.txt`
installed:

```
ruff check .
ruff format --check .
pytest
```

Also run `node --test tests/*.mjs` when the repo has Node tests, mypy when
the repo-specific notes list it, and the tests in a second venv with
`requirements_test_min.txt` when a change could behave differently on the
oldest supported Home Assistant. The standards check (also in CI) is
`python <path to bisman-automations/.github>/scripts/check_repo.py .`.

### Code and docs

- Support every Home Assistant from the `hacs.json` minimum to the newest
  release. Check for deprecations in the newest release and the beta.
- Keep entity IDs, unique IDs, service names and event names stable. When
  one has to change, migrate it and say so under Changed in the CHANGELOG.
- `strings.json` and `translations/en.json` hold the same keys. Home
  Assistant reads only `translations/`, so change both in the same commit.
- Never put personal details in the repo (README, CHANGELOG, code, tests,
  screenshots): no names, addresses, account or device identifiers, or real
  entity IDs. Use placeholders such as `light.living_room`.
- `README.md` is user documentation with the standard header (badges, HACS
  and "add integration" My buttons) and sections Installation, Setup, ...,
  Troubleshooting, Development, License. Use plain language and show names,
  not entity IDs, wherever the UI does.
<!-- END bisman-automations shared rules -->
