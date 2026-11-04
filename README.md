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
- Optional: to-do lists (for example Local To-do, or Apple Reminders synced to Home Assistant) for chores.

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
- **Chores.** Tap one, say who did it, and the points are added straight away.
- **Rewards.** Tap one and confirm. TV time is given on that TV in TV Mgmt at once; anything else waits for a parent to hand it out. Rewards you can't afford yet say how many more points you need, and one that can only be had once a day or once a week says when it's back.
- **Undo.** Tapped the wrong name or chore? Tap **Undo** on the message that pops up. It works for a minute, for a chore not checked yet and a reward not handed out yet; TV time is taken back off the TV.
- **Home.** The scenes, lights and other things a parent added. Tap one to use it: a scene or script starts, a light or switch turns on or off, blinds open or close, a lock locks or unlocks, and a speaker plays or pauses. Anything that asks first shows "Are you sure?". Sensors, thermostats and the weather are only shown. Each tile shows what it's doing now.
- **Lately.** What was done and spent recently.

To show it on a shared display, point the display's browser or kiosk app at `/family` on your Home Assistant. The display can be logged in as a user who isn't an admin: everyone can mark chores done and pick rewards, but only admins can check chores or change anything. The display can only use the home controls a parent put on the dashboard, nothing else.

### As a shared screen's default dashboard

Home Assistant only lets a login pick a dashboard as its default, and the Family page in the sidebar isn't one. So on the **Parents** dashboard, under **Family**, tap **Make a Family dashboard**. It makes a dashboard called **Family dashboard** that shows the Family page full screen. It's left out of the sidebar, since **Family** is already there.

Then log in on the shared screen as its user, open your profile, and pick **Family dashboard** under **Dashboard**.

You can also put the **Family** card (`custom:family-card`) on any dashboard yourself, for example in a panel view.

## The Parents dashboard

- **To check.** Chores the kids marked done. **Done right** keeps the points; **Didn't happen** takes them back (and puts a to-do item back on its list). Below are rewards still to hand out; mark them **Handed out**. To keep the list short, pick **Count chores nobody checked as done right** after a day or a week; those show as "checked automatically" in History.
- **Chores.** Add, edit or turn off chores. For each: its points, how often it can be done (every day, every week, or just once), and who can do it (nobody ticked means anyone). A chore for anyone is done once per day or week by whoever does it first; a chore for chosen people can be done by each of them.
- **Chores from to-do lists.** Every open item on these lists is a chore, worth the list's points. Put the points at the end of an item to change them: `Feed the dog [5]`, `Feed the dog (5 points)` or `Feed the dog - 5 pts`. When it's marked done, the item is ticked off its list, so a repeating reminder comes back when its list brings it back.
- **Rewards.** Add what points can buy: **TV time** (pick the TV and the minutes, and optionally give the whole home the same time) or **Something else** for a parent to hand out. **How often** limits each person to once a day or once a week, so all the points don't go on TV in one afternoon.
- **Home.** Pick what shows under **Home** on the Family dashboard, and in what order. Search for a scene, script, button, light, switch, fan, blind, valve, lock, speaker or TV, or for a sensor, thermostat or weather to show. Give it a different name or an emoji if you like, choose who sees it (nobody ticked means everyone), and tick **Ask "Are you sure?" first** for locks and doors. Anyone at the Family dashboard can use what's here, so only add what the kids may use.
- **Family.** Add, edit or remove family members, and add or take away points by hand, with a reason.
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
| `family_chore_reviewed` | A parent checked a chore, or it was counted as done automatically. | `member`, `member_id`, `chore`, `approved`, `automatic` (when counted automatically), `points`, `balance` |
| `family_reward_redeemed` | Points were spent on a reward. | `member`, `member_id`, `reward`, `points`, `balance` |

## Troubleshooting

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
