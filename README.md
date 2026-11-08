<p align="center">
  <img src="custom_components/family/brand/icon.png" alt="Family" width="128">
</p>

# Family

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.8%2B-blue.svg)](https://www.home-assistant.io/)
[![GitHub Release](https://img.shields.io/github/v/release/bisman-automations/ha-family)](https://github.com/bisman-automations/ha-family/releases)
[![Test](https://github.com/bisman-automations/ha-family/actions/workflows/test.yml/badge.svg)](https://github.com/bisman-automations/ha-family/actions/workflows/test.yml)
[![Validate](https://github.com/bisman-automations/ha-family/actions/workflows/validate.yml/badge.svg)](https://github.com/bisman-automations/ha-family/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/bisman-automations/ha-family)](LICENSE)

**Chores and rewards for the whole family, in Home Assistant.** Kids mark chores done on a shared screen and earn points straight away. They spend the points on rewards, such as TV time with [TV Mgmt](https://github.com/bisman-automations/ha-tv-mgmt) or anything you add. Parents check the chores later and take the points back if one didn't happen.

Chores and rewards are the first part of Family; more family tools will join them.

## Requirements

- Home Assistant 2026.8 or newer.
- For TV time rewards: [TV Mgmt](https://github.com/bisman-automations/ha-tv-mgmt) 1.20.0 or newer, with the TVs set up. With 1.21.0 or newer, TV Mgmt's Activity shows whose reward the time was, and its Live Activity on your phone counts down the time the kids earned.
- For music time rewards: [Media Mgmt](https://github.com/bisman-automations/ha-media-mgmt), with the speakers set up. With 1.5.0 or newer, its Activity shows whose reward the time was, and a reward can also give time to the whole home's limit.
- Optional: to-do lists (for example Local To-do, or Apple Reminders synced to Home Assistant) for chores.
- Optional: the Home Assistant app on the parents' phones, to check chores from a notification.

## Installation

### Marketplace (Home Assistant 2026.11 and newer)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=bisman-automations&repository=ha-family&category=integration)

1. Select the button above, or go to **Settings > Marketplace**, choose **Add
   from link**, enter `bisman-automations/ha-family` under **GitHub link**, and
   select **Add**. Adding a repository from a link needs a GitHub connection;
   the Marketplace asks you to connect one if you haven't.
2. Install **Family**. If a repair asks you to restart Home Assistant, restart it.

New versions show up under **Settings > Updates**.

### HACS (Home Assistant 2026.10 and older)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bisman-automations&repository=ha-family&category=integration)

1. Select the button above, or in HACS open the menu, choose **Custom
   repositories** and add `https://github.com/bisman-automations/ha-family` as an
   **Integration**.
2. Download **Family** and restart Home Assistant.

### Manual

1. Download `family.zip` from the [latest release](https://github.com/bisman-automations/ha-family/releases/latest).
2. Unzip it into `config/custom_components/family/` and restart Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up Family.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=family)

Select the button above, or go to **Settings > Devices & services > Add
integration** and search for **Family**. Family is set up once; there's nothing
to fill in. Two dashboards appear in the sidebar:

- **Family**, for everyone, made for a shared touch screen such as a wall tablet or a kitchen display.
- **Parents**, for Home Assistant admins only.

On the **Parents** dashboard:

1. Under **Family**, add each family member. Pick an emoji and a color, and link them to their Home Assistant person if they have one: its picture is used, and if they log in to Home Assistant, the Family dashboard opens on their own page.
2. Under **Chores**, add chores, and add any to-do lists whose items are chores.
3. Under **Rewards**, add what points can buy.
4. Under **Home**, add anything the family should be able to use or see from their dashboard, such as a movie-night scene, the playroom lights or the outside temperature.

## The Family dashboard

- **Who's here?** Everyone's picture and points. Tap yours to see only your chores and the rewards you can afford.
- **Notes.** Short notes and reminders for everyone, or for one person on their page. Tap **Add a note** to put one up from the screen, and ✕ to take it down. A note a parent put up can only be taken down by a parent. A note can show until a chosen day, then it goes by itself.
- **Today.** Today's events from the calendars a parent picked, all-day ones first. On someone's own page, their calendar and the family's.
- **Meals.** Today's and tomorrow's breakfast, lunch and dinner, as planned on the Parents dashboard.
- **Chores.** Tap one, say who did it, and the points are added straight away.
- **Rewards.** Tap one and confirm. TV time is given on that TV in TV Mgmt at once, and music time on that speaker in Media Mgmt; anything else waits for a parent to hand it out. Rewards you can't afford yet say how many more points you need, and one that can only be had once a day or once a week says when it's back.
- **Undo.** Tapped the wrong name or chore? Tap **Undo** on the message that pops up. It works for a minute, for a chore not checked yet and a reward not handed out yet; TV time is taken back off the TV.
- **Home.** The scenes, lights and other things a parent added. Tap one to use it: a scene or script starts, a light or switch turns on or off, blinds open or close, a lock locks or unlocks, and a speaker plays or pauses. Anything that asks first shows "Are you sure?". Sensors, thermostats and the weather are only shown. Each tile shows what it's doing now.
- **Saving up.** On your own page, tap a reward you can't afford yet and pick **Save for this**. Your page shows how far you are, and your picture on **Who's here?** has a little bar. Once you get it, you're done saving; tap it again and pick **Stop saving for it** to change your mind.
- **Turns.** A chore the kids take in turns says whose turn it is, and only they can do it.
- **Lately.** What was done and spent recently.

- **Done today.** What's finished today, ticked off.
- **Streaks.** 🔥 and the number of days in a row someone has done at least one chore.
- A reward someone can't afford yet shows how far they are ("15 of 25").

After 2 minutes without a tap, the dashboard goes back to **Who's here?**, so the next person doesn't land on someone else's page.

Each section shows its first row: as many tiles as fit across the screen. Tap **Show all** for the rest, or tap a section's name to fold it away. Each screen remembers which sections are open.

To show it on a shared display, point the display's browser or kiosk app at `/family` on your Home Assistant. The display can be logged in as a user who isn't an admin: everyone can mark chores done and pick rewards, but only admins can check chores or change anything. The display can only use the home controls a parent put on the dashboard, nothing else.

### As a shared screen's default dashboard

Home Assistant only lets a login pick a dashboard as its default, and the Family page in the sidebar isn't one. So on the **Parents** dashboard, under **Family**, tap **Make a Family dashboard**. It makes a dashboard called **Family dashboard** that shows the Family page full screen. It's left out of the sidebar, since **Family** is already there.

Then log in on the shared screen as its user, open your profile, and pick **Family dashboard** under **Dashboard**.

You can also put the **Family** card (`custom:family-card`) on any dashboard yourself, for example in a panel view.

## The Parents dashboard

- **To check.** Chores the kids marked done. **Done right** keeps the points; **Didn't happen** takes them back (and puts a to-do item back on its list). Below are rewards still to hand out; mark them **Handed out**. To keep the list short, pick **Count chores nobody checked as done right** after a day or a week; those show as "checked automatically" in History.
- **Chores.** Add, edit or turn off chores. For each: its points, when it **comes back**, and who can do it (nobody ticked means anyone). A chore for anyone is done by whoever does it first; a chore for chosen people can be done by each of them. A chore comes back:
  - **every day** or **every week** (from Monday), or it's done **just once**;
  - **some days after it's done**, for example 3 days after the plants were last watered;
  - **right away**, every time it's done, for something that can be done again and again;
  - **once a parent checks it**: it stays done while it's on **To check**.

  **Which days** shows a chore only on those days, such as Tuesday for the trash, and **Shown from** / **Until** only between those times, such as 6:00 AM to 9:00 AM for a morning chore (times can cross midnight). The Family dashboard changes on its own when a chore's time starts or ends.

  **They take turns** makes the people ticked under **Who can do it** take turns: it's only for whoever's turn it is, and the turn moves on each time it's done, each day or each week. Pick **Whose turn is it now?** to start or change it. If it didn't happen, it stays their turn.

  **Also keep it on a to-do list** puts the chore on a Home Assistant to-do list too. Family adds it while it can be done, ticks it off when it's done, and opens it again when it comes back. Renaming the chore renames the item, and removing the chore (or picking no list) removes it. Ticking or editing the item on the list yourself doesn't change the chore. If that list is also a chore list, the item isn't counted as a second chore.
- **Chores from to-do lists.** Every open item on these lists is a chore, worth the list's points. Put the points at the end of an item to change them: `Feed the dog [5]`, `Feed the dog (5 points)` or `Feed the dog - 5 pts`. When it's marked done, the item is ticked off its list, so a repeating reminder comes back when its list brings it back. To give single items their own points without changing their text, tap **Points for items** next to the list: each open item has its own box, and an empty box uses the list's points (or the points written in the item). Points are kept by the item's name, so a repeating item keeps its points when it comes back.
- **Rewards.** Add what points can buy: **TV time** (pick the TV and the minutes, and optionally give the whole home the same time), **Music time** (pick the speaker and the minutes, given in Media Mgmt, and optionally give the whole home the same time) or **Something else** for a parent to hand out. **How often** limits each person to once a day or once a week, so all the points don't go on TV in one afternoon.
- **Home.** Pick what shows under **Home** on the Family dashboard, and in what order. Search for a scene, script, button, light, switch, fan, blind, valve, lock, speaker or TV, or for a sensor, thermostat or weather to show. Give it a different name or an emoji if you like, choose who sees it (nobody ticked means everyone), and tick **Ask "Are you sure?" first** for locks and doors. Anyone at the Family dashboard can use what's here, so only add what the kids may use.
- **Bonus points** (under **Rewards**). Extra points when someone finishes all of their own chores for the day (chores anyone can do don't count), and every so many days in a row, for example 10 points every 7 days. A bonus goes away if its chore is undone or marked **Didn't happen**.
- **Penalties.** **Didn't happen** always takes a chore's points back. To take more, set **When a chore didn't happen, also take away** under **To check** for the whole family, or a **Penalty if it didn't happen** on a chore or to-do list. The box next to **Didn't happen** shows the penalty that will be taken; type a number to change it just this time. Marking it **Done right** later gives everything back.
- **Phones** (under **To check**). Pick the parents' phones (any phone with the Home Assistant app), and what to send: a notification **when a chore is marked done**, with **Done right** and **Didn't happen** buttons; one **when a reward needs handing out**, with a **Handed out** button; and **a summary of the week** every Sunday at 6:00 PM: each person's chores, points earned and spent, and how many chores are still to check. Only a parent's (admin's) phone can check a chore. Once a chore is checked anywhere, its notification goes away.
- **Meals.** Plan breakfast, lunch and dinner for the week ahead. Leave a meal empty to leave it out.
- **Notes.** Every note on the board, who put it up and until when. Put one up for everyone or for one person, or take any note down.
- **Family.** Add, edit or remove family members, and add or take away points by hand, with a reason. Each member can have an **allowance**: points added every week.
- **Allowance and money** (under **Family**). The day and time the weekly allowance is given (a week Home Assistant was off isn't made up), and optionally what one point is worth and a money sign, so points also show as money, like "42 points · $4.20".
- **Today's calendar** (under **Family**). Pick the calendars whose events show under **Today**, each for everyone or for one person.
- **History.** Everything done and spent. A chore found not done later can still be marked **Didn't happen** here.

## Entities

| Entity | What it shows |
| --- | --- |
| **{Member} points** (sensor) | The member's points. Attributes: `member`, `chores_to_check`. |

## Actions

| Action | What it does |
| --- | --- |
| `family.add_points` | Give a member points (negative to take them away), with an optional reason shown in the history. `member` is their name as set up in Family. |

```yaml
action: family.add_points
data:
  member: Alex
  points: 10
  reason: Good report card
```

## Events

For automations, for example to send a message or play a sound:

| Event | When | Data |
| --- | --- | --- |
| `family_chore_done` | A chore is marked done. | `member`, `member_id`, `chore`, `points`, `balance` |
| `family_chore_reviewed` | A parent checked a chore, or it was counted as done automatically. | `member`, `member_id`, `chore`, `approved`, `automatic` (when counted automatically), `points`, `penalty` (extra points taken), `balance` |
| `family_bonus_given` | Someone earned bonus points. | `member`, `member_id`, `bonus` (`all_done` or `streak`), `title`, `points`, `balance` |
| `family_reward_redeemed` | Points were spent on a reward. | `member`, `member_id`, `reward`, `points`, `balance` |

## Troubleshooting

- **A music time reward says Media Mgmt isn't set up.** Install Media Mgmt and set up the speaker, then pick the speaker again in the reward.
- **No phones to pick under Phones.** Install the Home Assistant app on the phone and log in to your Home Assistant; it adds the phone's notify action.
- **Tapping Done right on a phone does nothing.** Only phones logged in as an admin can check chores. The chore may also have been checked or undone already.
- **A TV time reward says TV Mgmt isn't set up.** Install TV Mgmt 1.20.0 or newer and set up the TV, then pick the TV again in the reward.
- **A to-do list's items don't show.** Check the list on the Parents dashboard under **Chores**, and that the to-do list itself is available in Home Assistant.
- **The Parents dashboard is missing.** It's only in the sidebar for admins.
- **A home control says it isn't available.** The device is offline or was removed from Home Assistant. Check it in Home Assistant, or remove it under **Home** on the Parents dashboard and add its replacement.

## Development

Run the shared checks in [CLAUDE.md](CLAUDE.md). To look at the dashboards
without Home Assistant, serve the repo root over HTTP and open
`scripts/panel-preview/index.html?mode=family` or `?mode=parents`
(add `&theme=dark` for the dark theme).

## License

MIT, see [LICENSE](LICENSE).
