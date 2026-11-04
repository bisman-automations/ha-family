# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-11-04

### Added

- **Done today.** A row on the Family dashboard with the chores finished today, ticked off, so kids see what they've done.
- **Saving up.** A reward someone can't afford yet shows how far they are: a bar and "15 of 25".
- **Streaks.** 🔥 and the number of days in a row each person has done at least one chore, on their picture and at the top of their page.
- **Bonus points.** Under **Rewards** on the Parents dashboard: extra points when someone finishes all of their own chores for the day, and every so many days in a row. A bonus goes away if its chore is undone or didn't happen. New event: `family_bonus_given`.
- **Penalties.** When a chore didn't happen, its points are taken back, and you can take more on top: a family-wide penalty under **To check**, a penalty for each chore or to-do list, or a number typed next to **Didn't happen** for just that time. Marking it done right after all gives everything back. `family_chore_reviewed` has the `penalty` taken.

### Changed

- **Back to "Who's here?"** After 2 minutes without a tap, the Family dashboard goes back to everyone, so the next person doesn't land on the last kid's page. Sections opened with **Show all** go back to their first row.
- **Quieter tiles on someone's own page.** Their own chores don't repeat their name and picture; shared chores keep their list's name.

- **Shorter Family dashboard.** Chores, Rewards, Home and Lately each show their first row, as many as fit across the screen (more on a landscape screen, fewer on a portrait one), with **Show all** for the rest. Tap a section's name to fold it away completely. Each screen remembers which sections are open.
- **Two tiles across on phones**, instead of one.

## [1.3.0] - 2026-11-04

### Added

- **Points for single to-do items.** On the Parents dashboard, **Points for items** next to a chore to-do list gives each open item its own points, without changing its text. An empty box uses the list's points or the points written in the item. Repeating items keep their points when they come back.

## [1.2.0] - 2026-11-04

### Added

- **Family as a shared screen's default dashboard.** Home Assistant only offers dashboards as a login's default, not sidebar pages like Family. On the **Parents** dashboard, under **Family**, **Make a Family dashboard** makes a dashboard that shows the Family page full screen. Then pick **Family dashboard** as the default dashboard in the shared screen login's profile.
- **Family card.** The Family page as a card (`custom:family-card`), for any dashboard.

## [1.1.1] - 2026-11-04

### Fixed

- **A Home Assistant person can only be linked to one family member.** When adding or editing a family member, people already linked to someone else aren't offered. Picking a person also fills in an empty name with their first name.

## [1.1.0] - 2026-11-04

### Added

- **Undo.** A mistaken tap on the Family dashboard can be undone for a minute with **Undo** on the message that pops up: a chore not checked yet, or a reward not handed out yet. TV time is taken back off the TV.
- **How often a reward can be had.** Each reward can be limited to once a day or once a week for each person. On the Family dashboard it shows **Again tomorrow** or **Again next week** until then.
- **Checking chores automatically.** On **To check**, chores nobody checked can count as done right after a day or a week. They show as "checked automatically" in History, where any chore can still be marked **Didn't happen**.
- **Whose reward it was in TV Mgmt.** With TV Mgmt 1.21.0 or newer, its Activity shows the time as "Alex's reward: 30 minutes of TV". Older TV Mgmt still gets the time.

## [1.0.0] - 2026-11-04

### Added

- **Chores and rewards.** The first family tool:
  - **Family dashboard** for everyone, made for a shared touch screen. Tap who you are, mark chores done for points straight away, and spend points on rewards.
  - **Parents dashboard** for admins. Check chores (**Didn't happen** takes the points back), hand out rewards, and edit chores, rewards and family members. Points can be changed by hand, and the history shows everything.
  - **Chores** added on the dashboard (every day, every week or just once, for anyone or for chosen people), and from to-do lists, with points written at the end of an item like `Feed the dog [5]`.
  - **Rewards:** TV time on a chosen TV through TV Mgmt, optionally for the whole home too, or anything else a parent hands out.
  - **Home controls.** Parents put scenes, scripts, lights, switches, blinds, locks, speakers and more on the Family dashboard, where a tap uses them. Sensors, thermostats and the weather can be shown too. Each can be shown to everyone or to chosen people, and can ask "Are you sure?" first.
  - A **points** sensor for each family member, the `family.add_points` action, and events for chores and rewards.

[1.4.0]: https://github.com/bisman-automations/ha-family/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/bisman-automations/ha-family/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/bisman-automations/ha-family/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/bisman-automations/ha-family/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/bisman-automations/ha-family/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/bisman-automations/ha-family/releases/tag/v1.0.0
