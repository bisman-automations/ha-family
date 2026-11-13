# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.16.1] - 2026-11-13

### Changed

- **Chores are ticked off with a check box.** Each chore has a round check box: tap it to tick the chore off. Tapping the rest of the tile does nothing, so a stray tap or a scroll doesn't tick anything off.

## [1.16.0] - 2026-11-13

### Added

- **One tap to tick a chore off.** On someone's own page, tapping a chore ticks it off for them straight away, with **Undo** in the message at the bottom. A chore only one person can do is ticked off for them from any page. Only a chore several people could have done asks who did it.
- **A cheer when someone's done.** Finishing all of their own chores for the day plays a short confetti cheer. Tap it to close it.
- **Progress on each picture.** Each person shows how many of their own chores are done today (✓ 2/3), green once they're all done.

### Changed

- **A parent's chores don't need checking.** Chores done by someone linked to a Home Assistant administrator (anyone who can open the Parents dashboard) count as done right straight away, and don't send a notification.

## [1.15.0] - 2026-11-11

### Changed

- **Who can get a reward is the list of people.** On the Parents dashboard, under **Rewards**, there is no Everyone checkbox and no Everyone row. The list is the family, and a new reward starts with all of them selected. Leave them all selected and the reward is for anyone, including people you add later. Untick people to limit it to those still selected. Untick all of them and nobody can get it. Rewards you already saved stay as they are until you save them again.

## [1.14.0] - 2026-11-11

### Added

- **Pick who can get each reward.** On the Parents dashboard, under **Rewards**, each reward is for everyone unless you choose people. The Family dashboard and the Family card only show a reward to someone it is for, and getting it is refused for anyone else, from the dashboard or anywhere else. Rewards you already have stay for everyone. If the last person a reward was for is removed, nobody can get it until you choose someone; it does not go back to everyone. The points sensor lists the rewards that person can get, and `family_reward_redeemed` says who the reward is for.

### Changed

- The README describes the whole of Family, and the install steps lead with the Marketplace (Home Assistant 2026.11 and newer), then HACS (2026.10 and older), then adding the repository yourself, then installing by hand.
- Test tools: ruff 0.17.4.

## [1.13.1] - 2026-11-09

### Fixed

- **A chore someone did today stays done for them all day.** A chore of their own that comes back once a parent checks it no longer shows as still to do (and holds back their all-done bonus) after you check it.

### Changed

- **Missed instead of to do.** A chore of their own whose hours are over for the day (say 6:30 to 8:00 AM) now shows as **missed** on their picture and under **Going for**, instead of **to do**.

## [1.13.0] - 2026-11-09

### Added

- **To-do lists can show items only when they're due.** Set a list's **When items show** to **Only when due today or overdue**: items due on a later day stay off the Family dashboard until their day, an item with a due time shows once that time comes, and items with no due date always show. The Family dashboard updates on its own when an item becomes due.

## [1.12.0] - 2026-11-09

### Added

- **Single to-do items can be for certain people.** Next to each item under **Points for items**, tick who it's for. With nobody ticked, it's for the people ticked for the whole list, as before. Like an item's own points, they're kept by name, so a repeating item keeps them when it comes back.

## [1.11.1] - 2026-11-09

### Fixed

- **Everyone's page shows only chores up for grabs for everyone.** A chore or to-do list up for grabs for some people (like a list for the parents) now shows only on those people's pages, not on everyone's.

## [1.11.0] - 2026-11-09

### Added

- **Who does what.** The Parents dashboard's **Chores** tab starts with every chore lined up against each person: their own, taking turns (and whose turn it is now), or up for grabs, grouped by kind, with how many of their own chores each person has done today. Tap the heading to fold it away.

### Changed

- **Family is in the HACS default list.** The install steps now start with searching for **Family** in the Marketplace or HACS; adding it from a link or as a custom repository is only needed if the search doesn't find it.

## [1.10.0] - 2026-11-09

### Added

- **My chores and Up for grabs.** On someone's page, **My chores** are theirs to do and **Up for grabs** are extra: whoever does one first gets the points. Everyone's page shows only what's up for grabs, and each person's picture says how many of their own chores are left today, or **All done**.
- **Up for grabs for some people.** A chore or to-do list with people ticked can now be **Up for grabs** for just them (whoever's first) instead of each one's own chore. Pick it under **How it's done**. A chore with nobody ticked is up for grabs for everyone, as before.
- **Going for.** Each person's page starts with what they're working toward: how many of today's own chores are done and the bonus for finishing, their streak and the next streak bonus, and the reward they're saving for.

### Changed

- **A streak now means days in a row with all of their own chores done.** Doing a chore up for grabs no longer keeps it going, and a day with none of their own chores doesn't break it. Streaks going on now carry over. With the all-done bonus at 0 points, finishing the day still counts for the streak.
- **Chores come first on each page**, right under **Going for**.

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

[1.16.1]: https://github.com/bisman-automations/ha-family/compare/v1.16.0...v1.16.1
[1.16.0]: https://github.com/bisman-automations/ha-family/compare/v1.15.0...v1.16.0
[1.15.0]: https://github.com/bisman-automations/ha-family/compare/v1.14.0...v1.15.0
[1.14.0]: https://github.com/bisman-automations/ha-family/compare/v1.13.1...v1.14.0
[1.13.1]: https://github.com/bisman-automations/ha-family/compare/v1.13.0...v1.13.1
[1.13.0]: https://github.com/bisman-automations/ha-family/compare/v1.12.0...v1.13.0
[1.12.0]: https://github.com/bisman-automations/ha-family/compare/v1.11.1...v1.12.0
[1.11.1]: https://github.com/bisman-automations/ha-family/compare/v1.11.0...v1.11.1
[1.11.0]: https://github.com/bisman-automations/ha-family/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/bisman-automations/ha-family/compare/v1.9.0...v1.10.0
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
