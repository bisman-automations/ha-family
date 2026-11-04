# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.1.1]: https://github.com/bisman-automations/ha-family/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/bisman-automations/ha-family/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/bisman-automations/ha-family/releases/tag/v1.0.0
