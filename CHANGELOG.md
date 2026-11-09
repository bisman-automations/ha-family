# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.9.0] - 2026-11-08

### Added

- **Get a reward together.** Tap a reward, then **Get it together**, and pick who's putting in points. The points are shared as evenly as everyone's points allow: someone with fewer puts in what they have and the others cover the rest. The points are held until a parent says yes on the Parents dashboard (**To check**) or from their phone; **No** gives everyone their points back. TV and music time is given as soon as a parent says yes.
- **Next few days.** The **Today** section has a **Next few days** button that opens today, tomorrow and the five days after in a pop-up, each with its events.

### Changed

- **Events that are already over stay under Today**, faded and marked **Over**, instead of looking like they're still to come.
- **The Today section shows whenever calendars are picked**, with "Nothing today" on a quiet day, so **Next few days** is always there.

## [1.8.0] - 2026-11-08

### Added

- **The Family dashboard has a tab for each person.** **Make a Family dashboard** now makes a **Home** tab for everyone and a tab for each family member, showing only their page. Someone's tab stays on their page, so a tablet in a child's room can show just their chores.
- **The tabs follow the family.** Adding, renaming or removing someone on the Parents dashboard adds, renames or removes their tab. Cards and tabs you add to the dashboard yourself are kept. Once the dashboard is there, the button reads **Update the Family dashboard**; tap it to bring an existing dashboard up to date with the new tabs.
- **The Family card can show one person.** Give it `member:` and that person's id to put just their page on any dashboard.

## [1.7.0] - 2026-11-08

### Added

- **Music time for the whole home.** A music time reward can also give the whole home the same time, like TV time rewards can. It needs Media Mgmt 1.5.0, which added whole-home limits. Undoing the reward takes that time back too.

## [1.6.0] - 2026-11-07

### Added

- **Chores on set days and times.** Pick the days a chore is on (the trash on Tuesdays), and the hours it shows (6:00 AM to 9:00 AM for a morning chore, or a bedtime chore that runs past midnight). The Family dashboard changes on its own when a chore's time starts or ends.
- **Taking turns.** The people picked for a chore can take turns: it's only for whoever's turn it is, and the turn moves on each time it's done, each day or each week. The Family dashboard says whose turn it is, and a chore that didn't happen stays their turn.
- **Saving for a reward.** On their own page, kids tap a reward they can't afford yet and pick **Save for this**. Their page shows how far they are, with a little bar on their picture too.
- **Check chores from your phone.** Under **To check** → **Phones**, pick the parents' phones. They get a notification when a chore is marked done, with **Done right** and **Didn't happen** buttons, and when a reward needs handing out, with **Handed out**. Only a parent's phone can check a chore, and the notification goes away once it's checked anywhere.
- **A weekly summary.** Every Sunday at 6:00 PM: each person's chores, points earned and spent, and how many chores are still to check.
- **Music time rewards.** Kids can spend points on listening time on a speaker in [Media Mgmt](https://github.com/bisman-automations/ha-media-mgmt), given straight away like TV time.
- **Notes.** A board of short notes on the Family dashboard: "Dentist at 4", "Library books due Friday". Anyone can put one up from the screen, for everyone or for one person, and a note can go away by itself after a chosen day. A parent's note can only be taken down by a parent. Parents also see and manage them under the new **Notes** tab.
- **Today's calendar.** Pick calendars under **Family → Today's calendar**, each for everyone or for one person, and today's events show on the Family dashboard under **Today**.
- **Meals for the week.** Plan breakfast, lunch and dinner under the new **Meals** tab. Today's and tomorrow's show on the Family dashboard.
- **Allowance.** Give each family member points every week, on the day and time you pick under **Family → Allowance and money**.
- **Points as money.** Set what a point is worth and a money sign, and everyone's points also show as money.

### Changed

- Test tools: ruff 0.17.3.

## [1.5.0] - 2026-11-06

### Added

- **Chores that come back once they're done.** Besides every day, every week and just once, a chore can come back some days after it was done (for example 3 days after the plants were watered), right away every time it's done, or once a parent checks it.
- **Dashboard chores on a to-do list too.** A chore made on the Parents dashboard can also be kept on a Home Assistant to-do list: it's added while it can be done, ticked off when it's done and opened again when it comes back. Renaming or removing the chore updates the list, and the item isn't counted twice if that list is also a chore list.

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

[1.9.0]: https://github.com/bisman-automations/ha-family/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/bisman-automations/ha-family/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/bisman-automations/ha-family/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/bisman-automations/ha-family/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/bisman-automations/ha-family/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/bisman-automations/ha-family/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/bisman-automations/ha-family/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/bisman-automations/ha-family/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/bisman-automations/ha-family/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/bisman-automations/ha-family/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/bisman-automations/ha-family/releases/tag/v1.0.0
