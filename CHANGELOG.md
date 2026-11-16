# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.15.3] - 2026-11-15

### Changed

- **Screenshots in the README.** The README now shows the Family dashboard (on a big screen, a phone and in the dark theme) and the Parents tabs: To check, Who does what, Rewards and History.

## [2.15.2] - 2026-11-15

### Changed

- **Parents' history numbers kept between refreshes.** Week by week, Points over time and each entry's points before and after are worked out once and kept until the history changes (a chore done, one marked as didn't happen, points changed), instead of again for every open screen after every change. A parents' refresh with a year of history went from about 15 ms to under 10 ms on a test machine.
- **Lately without sorting.** The newest entries come straight from the history's time order instead of sorting the whole year each time.

## [2.15.1] - 2026-11-15

### Changed

- **A faster dashboard for a busy family.** The Family dashboard now finds a chore's, a person's or a day's history in one look instead of reading the whole year's history for every chore, person and goal. With a year of history, each refresh went from about 150 ms to about 16 ms on a test machine. Points, streaks, badges and goals add up exactly as before.
- **Only this week's chores read.** Whether a chore is done today or this week is worked out from completions since the day or week began, not from all of them.
- **One update at a time.** Checking several chores at once, or a chore with its bonuses, tells the dashboards and sensors once instead of once per change.
- **Badges checked when something changed.** Badges are looked for again only when history, reviews, people or the day changed.
- **Goals read from their start.** A family goal only reads history since the goal began.
- **Own chores worked out once.** Each person's own chores today (total, left and missed) are worked out once per refresh instead of three times.
- **Quiet when nobody's looking.** A Family dashboard in a hidden tab or on a switched-off wall screen waits and loads once when it's seen again, and a change that comes in while it's loading leads to one more load, not several.

## [2.15.0] - 2026-11-15

### Added

- **Shop days.** A reward can be bought only on the days you tick, such as Saturday, so the kids save up during the week. The tile says when.
- **Swap market.** Chores offered to anyone show on the Family dashboard in one place; tap one to take it (on everyone's page it asks who).
- **Points for grades.** A **Grades** card under To check gives points for a report card or a test, from a grade table you set (A=10, B=6, C=2 to start).
- **Theme week.** A week with a theme, such as "Kind words". Each day the kids tap that they kept it, and you check it like a chore.
- **Helping out.** Extra points for each helper when a chore is marked done with helpers.
- **Money paid out.** Under **History**, each month's cash outs and how much was paid, per child, with a spreadsheet download.
- **Goal milestones.** A family goal's tile cheers at a quarter, halfway and three quarters, and the new `family_goal_milestone` event fires once at each.

## [2.14.0] - 2026-11-15

### Added

- **Kids-only goals.** A family goal can be just for the kids: only their points count toward it, and it doesn't show on the parents' own pages. A goal can also be for some of you, such as two brothers saving together.
- **Trade a chore for the week.** When offering a chore, tick **For the rest of the week** and it's theirs through Sunday, not just today.
- **Keep your points.** With the saving bonus on, a kid's page shows what they'll get on allowance day if they keep their points until then.
- **Homework timer.** Kids start a timer on the Family dashboard when they sit down to homework and stop it when they're done; points for every so many minutes, checked like a chore.
- **Photos of the month.** Under **History**, every chore photo from this month (or last) on one page, to look back on or print.
- **How hard a chore is, and points by age.** Mark chores easy, medium or hard (shown as stars on the tile). Older kids can get a percentage more points for each year over an age you pick.
- **Rewards to buy go on a list.** Pick a to-do list, and when someone gets a reward a parent hands out, "A new toy for Alex" is added to it.

### Changed

- The `family_goal_reached` event also has `members` and `kids`.

## [2.13.0] - 2026-11-15

### Added

- **More than one family goal.** Up to six goals at a time, such as Pizza night and a movie projector night. Points from everyone's chores count toward each one, and each has its own bar on the Family dashboard. Your one goal from before becomes the first.
- **Chore auctions.** Put a bigger job up for auction for a while. The kids bid how few points they'd do it for; when time's up (or you close it) the lowest bid gets it as their chore, worth their bid.
- **Allowance rules.** Last week's chores can change this week's allowance: up when they finished all their chores every day, down when they finished them on fewer than half the days. The history says why.
- **Reading log.** Points for every so many minutes read, up to a daily limit. The kids log it (and the book) on the Family dashboard, and you check it like a chore.
- **Team chores.** Everyone on the chore ticks it, and nobody's points count until they all have. The tile shows how many have done it.
- **Gift ideas.** The kids add what they'd like on their own page. Under **Rewards**, **Share** sends their ideas and wishlist to grandparents, or copies them.
- **Screen-time bank.** For a TV a child uses on their own, the minutes TV Mgmt says are left at night are saved, up to a limit, and they can use them another day.
- **Beat the clock.** Bonus points for finishing a routine (such as Morning) before it's time to leave.

### Changed

- The `family_goal_reached` event now also has the goal's `id`.

## [2.12.0] - 2026-11-15

### Added

- **Quests.** A bigger job in steps, such as clearing out the garage. The steps open one at a time, and whoever does one gets its points.
- **Pet care.** Each pet's meals or walks at set times, ticked off once each from an hour before, so nobody feeds the dog twice. Checked and undone like chores.
- **Save your streak.** A streak freeze turns a sick day into a day off, for points a parent sets, once a week.
- **Paying for a trade.** A child can add some of their points for whoever takes a chore they're trading.
- **Wishlist.** Kids mark up to three rewards they want most; parents see **Most wanted**.
- **Pocket money statements.** One person's month, like a bank statement, to show or print.
- **Quiet hours.** The shared screen rests at night: a big clock, time to leave and notes, until someone taps it.

## [2.11.0] - 2026-11-15

### Added

- **Chore bingo.** Each person gets a 3×3 card of nine of their chores every Monday. Doing a chore marks its square, and every line, and the whole card, earns points.
- **Races.** A child challenges a brother or sister: the first to finish all of today's own chores wins the points.
- **The give jar.** Set something the family gives for. The kids give points from their own page, and a share of each allowance can go in by itself.
- **Offer to do a chore.** Kids suggest a chore that isn't on the list and what it's worth; a parent's yes makes it a one-off chore of theirs.
- **How was today?** An evening check-in: each person taps how their day was. Only parents see the last two weeks, under History.
- **Time to leave.** A countdown across the top of the Family dashboard and the wall view on mornings with a leave time.
- **Chores that wait for something, or start something.** A chore can show only while something shows a state (Daily Routine's Kind of day, the house mode…), and finishing it can start a script, scene or button.

## [2.10.0] - 2026-11-15

### Added

- **Fair turns.** A chore taken in turns can now go **Fairly**: to whoever has done it least in the last 30 days, so a missed turn evens out instead of being skipped.
- **Match on saving up.** Under **Family**, set a percent a parent adds when someone gets the reward they're saving for. At 25%, a 100-point reward takes 80 of their own points. The goal tile shows the lower price, and the match shows in History.
- **TV time for chores done.** With TV Mgmt, a family member can get minutes of TV (on one TV, or the whole home too) as soon as they finish all of their own chores for the day. Undoing a chore takes the time back.
- **A kid's own phone.** `/family#me`, or the Family card with `phone: true`, opens straight on the signed-in child's page with only their sections and no way to switch to someone else.
- **Family meeting.** Under **History**, **Family meeting** shows this week for everyone, with what to talk about (chores that didn't happen, and why) and each person's chores for next week.
- **How to do a chore.** A chore can have a few lines on how it's done and an example photo of it done right. An **ⓘ** on its tile shows them, and **Read it to me** reads them aloud.
- **Helping out.** When the Family dashboard asks who did a chore, **Did someone help?** splits the points between whoever helped. Each share shows in that person's History, and undo takes them all back.
- **Mobile view for links.** Each link has **Mobile view**, on to start: the page shows at phone width, the way most school and club sites look best. Untick it for a site that needs the whole width.

## [2.9.0] - 2026-11-15

### Added

- **Photos of chores done.** A chore can ask for a photo when it's marked done, or need one. The camera opens on the Family dashboard, and **📷 Photo** shows it under **To check**. Photos are kept for two weeks.
- **A chore's own streak.** **Bonus every … days in a row** gives a chore's streak points each time the same person has done it that many days (weeks, for a weekly chore) running.
- **Pick your chores.** Chores in the pick-your-chores pool are nobody's until someone picks them for the week. **Pick your chores** on the Family dashboard shows whose turn it is (whoever has picked the fewest points goes next), with an optional limit on how many points each picks.
- **Money owed.** Under **Rewards and cash outs to hand out**, each person's unpaid cash outs are added up, with **Paid it all**.
- **Wall view.** A big view of everyone's points and today's chores for a TV or a tablet on the wall: `/family#wall`, or the Family card with `wall: true`.
- **Chores a device finishes.** **Done when this device… changes to** marks a chore done when, say, the robot vacuum docks or the dishwasher door opens. Whoever started the device from Home Assistant gets the points; otherwise **Who did this?** on the Family dashboard asks.

### Changed

- **Editing opens in place.** **Edit** on a chore, to-do list, reward, routine, Home tile or family member opens its form right under it, pushing the ones below down until you save or cancel, instead of at the bottom of the list.
- **Speakers fold away.** In a chore's **Say it on a speaker**, the speakers are a list you open, showing the ones picked when it's closed, with the picked ones first and a search box when there are many.

## [2.8.0] - 2026-11-15

### Added

- **Icons for chores.** A chore's picture can now be an icon as well as an emoji, for chores that have no emoji, such as vacuuming. Tap the picture to pick one: search over a hundred chore and home icons (vacuum, robot vacuum, mop, dishwasher, laundry, dog, lawn mower, snow shovel…), tap an emoji, or type any emoji. Any of Home Assistant's icons works, by its full name (such as `mdi:washing-machine`). Rewards, routines, family members, quick points, the family goal, countdowns, links and to-do items pick their pictures the same way.

## [2.7.0] - 2026-11-15

### Added

- **Check every chore at once.** When there's more than one chore to check, **Done right** and **Didn't happen** above the list check them all. **Didn't happen** asks first, and lets you say why once for all of them; each chore still takes back its own points and its own penalty (the number typed in its box, or the chore's, or the family's). A chore marked done while you were looking isn't checked with the rest.

## [2.6.0] - 2026-11-14

### Added

- **History, made easier to follow.** On the Parents dashboard's History tab:
  - Each entry shows that person's points just before and after it, for example 12 → 13.
  - Entries are grouped by day, with what was earned and taken that day.
  - **Points over time**: a chart of each person's points over the last four weeks.
  - A **Type** filter: chores, rewards, bonuses, points taken away, allowance, changed by hand or high fives.
  - **Done right** on a chore marked Didn't happen, to put it back.
  - Which parent checked a chore, handed out a reward or changed points ("· by Dana").
  - **Show more** for older entries, and **Spreadsheet** to download what's shown.
- **Why it didn't happen.** Marking a chore **Didn't happen** asks why, with quick choices or your own words. The reason shows in History and on the child's page.
- **New on the Family dashboard:**
  - **Read it to me**: 🔊 on chores and routine steps reads them aloud. **Picture mode** (per person) shows big pictures instead of words.
  - **Tomorrow**: tomorrow's chores and events.
  - **Screen time left** on each TV Mgmt TV and Media Mgmt speaker.
  - **Chore timer**: a countdown on a chore's tile, with a bonus for beating it.
  - **High fives**: a no-points thank-you from one person to another.
  - **Points story**: tap your points to see what earned and spent them, with before → after.
  - **Family streak**: days in a row everyone finished their own chores.
  - **What to wear**: today's weather in kid terms, from a weather entity you pick.
  - **Links**: web pages a parent adds, such as the school lunch menu, opened over the dashboard with no address bar.
- **Chores by age.** With a person's birthday and year born set, a chore can have a youngest and oldest age; only people that age see and do it.

## [2.5.0] - 2026-11-14

### Added

- **Countdowns.** "12 days to the beach" on the Family dashboard, under a new **Coming up** section. Parents add them under **Notes**, for everyone or for one person. Birthdays count down by themselves from a month before.
- **Ask for a reward.** On their own page, a child can ask for something that isn't on the list (with how many points they think it's worth). Parents see it at the top of **To check**, with a phone notification, and say yes with what it costs (it becomes a reward just for that child) or no.
- **Vote on dinner.** Parents give two to six choices under **Meals**; everyone taps one on the Family dashboard. When it closes, by its time or by hand, the winner goes on the meal plan as dinner.
- **Away.** Under **Family**, set when the family is away. Chores and routines are off, nothing counts as missed, streaks skip those days, and the weekly allowance isn't given. **We're back home** turns it off.
- **Double points.** Under **Chores**, make chores worth two or three times their points until a time you pick, for every chore or just some. The Family dashboard shows it at the top and on each chore.
- **Seasonal chores.** A chore can show only between two days of the year, such as raking leaves in the fall or shoveling the walk December to March.
- **Shopping list from the meal plan.** Add what each day needs under **To buy**, then put everything the coming week needs on a Home Assistant to-do list in one tap. What's already on the list isn't added again.
- **Saving bonus.** A percent of the points each person kept all week, given with the allowance, with an optional limit.
- **Birthdays.** Set each person's birthday: the Family dashboard wishes them a happy birthday, and they can get birthday points.
- **Add calendar events** from the parent controls, under **Notes**, to any of the family's calendars.
- **Weekly report.** Under **History**, a week for everyone (chores, points, rewards, badges, streaks) to print or share.

### Changed

- The Family dashboard has two new sections, **Coming up** and **What's for dinner?**. If you set your own section order, they're added at the end; move them under **Family** → **Family dashboard sections**.

## [2.4.0] - 2026-11-14

### Added

- **Hold rewards.** On the Parents dashboard's **Family** tab, **Hold rewards** next to someone puts their rewards on hold for the rest of today, 1 to 3 days, a week, or through a day you pick, with an optional reason they'll see. Until then they can't get a reward, alone or together, or cash out. Chores still earn points, and rewards they can't afford yet can still be saved for. Their Rewards section says until when, and **Lift the hold** ends it early. The event `family_rewards_held` lets automations follow along.

## [2.3.0] - 2026-11-13

### Added

- **Quick points for some of the family.** Each quick points button has its own list of who it's for. Leave everyone ticked and it shows for the whole family, including people you add later; untick people and it shows only next to whoever is still ticked. Buttons you already have stay for everyone.

### Fixed

- **Tidy quick points and to-do item boxes.** The emoji and name boxes when changing quick points, and the emoji boxes on to-do items, now look like the other boxes.

## [2.2.0] - 2026-11-13

### Added

- **Each parent's own PIN.** Next to the family PIN, every parent with an administrator's login can set their own PIN under **Family** → **Parent PIN**. Either one opens the parent controls on the shared screen, and **Back to Family** shows whose PIN opened them. Only you can change your own PIN, it stops working if your login stops being an administrator, and no two PINs can be the same.

## [2.1.0] - 2026-11-13

### Added

- **Badges.** First chore, 10, 50 and 100 chores, All done, 3-day, week and 30-day streaks, First reward and Cashed out. They show under someone's name on their page, pop up when earned, and stay once earned. The new `family_badge_earned` event is for automations.
- **Trading chores.** The ⇄ on one of your own chores offers it for today, to one person or anyone. Someone takes it, a parent says yes under **To check**, and they do it today instead.
- **Cashing out.** With a point value set, **💰 Cash out** turns points into money. The points are taken right away; a parent marks it **Paid**, or cancels it to give the points back.
- **Week by week.** The top of **History** shows each person's points earned and spent, and chores done, for each of the last 8 weeks.
- **Ask Assist.** "I finished feed the dog", "How many points do I have?" and "What chores do I have left?" work with Assist by voice or typing. A chore done this way still waits for a parent's check.

## [2.0.0] - 2026-11-13

One Family page for everyone: the Parents sidebar page is now part of it. Nothing else changes: your family, chores, points, entities, actions and events stay as they are.

### Changed

- **Parents is a button on the Family page.** The sidebar has one **Family** entry for everyone. **Parents** at the top switches the page to the parent controls, and **Back to Family** switches back. The **Family** card on a dashboard has the same button, so the wall tablet works the same way.
- **The old Parents link still works.** `/family-parents`, and the parents' notifications that open it, go to the Family page already switched to the parent controls.

### Added

- **Parent PIN for the shared screen.** Set a 4 to 8 digit PIN in the parent controls under **Family** → **Parent PIN** (from an administrator's login). On any login that isn't an administrator, such as the shared tablet, **Parents** asks for it. Administrators go straight in.
- **The parent controls close on their own.** On the shared screen they stay open until **Back to Family**, or until nobody has tapped for two minutes.
- **Wrong PINs lock the pad.** After five wrong PINs in a row the pad locks for five minutes and the parents' phones get a notification. Home Assistant only keeps a scrambled copy of the PIN.

### Removed

- **The Parents entry in the sidebar.** Use **Parents** on the Family page instead. Bookmarks and phone shortcuts to `/family-parents` keep working.

## [1.22.0] - 2026-11-13

### Added

- **Live Activities of today's chores.** Under **To check** → **Phones**, pick one or both:
  - **One for the family**: each child's progress on one line, such as "Alex 3/5 · Sam ✓". It says **All done today!** once everyone's finished.
  - **One for each child**: their own progress bar, "2 of 4 done · 2 to go". It says **All done!** for a couple of minutes once they finish, then goes away. Tapping it opens the Family dashboard.

  Set **Show from** to when the kids get up, such as 6:30 AM, so iPhone's 8-hour limit covers the day. They update as chores are done, count only children's own chores, and start fresh each day.
- **Filter History.** On the Parents **History** tab, pick someone under **Who**, or search for a chore, reward or bonus.

### Changed

- **Smoother updates.** The points sensors now tell Home Assistant how many updates they can take at once, as Home Assistant recommends. Nothing changes in how they look or work.

## [1.21.0] - 2026-11-13

### Added

- **Routines.** Step-by-step checklists such as Morning or Bedtime, in their own **Routines** tab on the Parents dashboard. Give a routine its steps, the points for finishing it, who does it, and which days and hours it shows. On the Family dashboard, tap a routine to open its checklist and tick the steps off one at a time. Ticking the last step finishes it: the points are given straight away, there's a celebration, and it waits under **To check** like a chore. Ticked steps start fresh each day. The Family dashboard gets a **Routines** section, which can be moved like the others.

## [1.20.0] - 2026-11-13

### Added

- **Family goal.** Set something the whole family works toward together, such as Pizza night at 200 points, at the top of **Rewards** on the Parents dashboard. Points from everyone's chores count toward it, and nobody spends any. The Family dashboard shows how far everyone has got under **Going for**, on every page. When it's reached, the `family_goal_reached` event fires, for an automation if you like.
- **Speaker reminders.** Pick a voice under **Family** → **Speaker reminders**. Then, on a chore, set a time and speakers under **Say it on a speaker**. At that time the speakers say who still has it to do, such as "Reminder for Alex and Sam: Set the table." Nothing is said once it's done.

### Fixed

- **Turn settings stay hidden** on the chore form until **They take turns** is ticked.

## [1.19.0] - 2026-11-13

### Added

- **Leave single to-do items out of the chores.** Under **Chores from to-do lists**, tap **Points for items** and tick **Leave out** next to an item that isn't a chore, such as a bill to pay. It stays on the to-do list but never shows on the Family dashboard. Untick it to bring it back. Left-out items move into a folded **Left out** group at the end of the list, so the rows you use stay short.
- **Quick points.** At the top of **To check**, one-tap buttons give or take points for the things you want to notice, such as "💛 Kind to a sibling +2" or "🙉 Not listening −1". Each tap shows in History. Tap **Change the buttons** to set your own, up to 12.

## [1.18.0] - 2026-11-13

### Added

- **Hide empty sections.** On the Parents dashboard, under **Family** → **Family dashboard sections**, tick **Hide sections with nothing in them** to leave out sections that are empty, such as **Up for grabs** when nothing is up for grabs. **Notes** always shows, so a note can still be added.
- **A chore kept on a to-do list shows the list's name** on its tile, like a chore from a to-do list does.

### Fixed

- **Each chore shows once.** A to-do item with the same name as a chore, or as another item on a list, no longer shows as a second tile. The Family dashboard shows chores first, then each to-do item once.
- **Folded cards stay folded.** A folded card on the Parents dashboard (such as **Allowance and money** or **Today's calendar**) no longer opens again after a save. It stays folded until you tap its title.

## [1.17.0] - 2026-11-13

### Added

- **Move the Family dashboard's sections around.** On the Parents dashboard, under **Family** → **Family dashboard sections**, move each section up or down. Every screen shows them in that order.
- **Emojis for single to-do items.** Next to each item in **Points for items**, pick an emoji to show on its tile.
- **Fold any card on the Parents dashboard.** Tap a card's title to fold it away, like **Who does what**. Each device remembers which are folded.
- **When a chore shows.** A chore kept on a to-do list can show only when its item is due today or overdue.

### Changed

- **No more doubled to-do items.** When a chore is kept on a to-do list that already has an item with the same name, Family ticks off that item instead of adding a second one. Removing the chore leaves that item on the list.

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

[2.15.3]: https://github.com/bisman-automations/ha-family/compare/v2.15.2...v2.15.3
[2.15.2]: https://github.com/bisman-automations/ha-family/compare/v2.15.1...v2.15.2
[2.15.1]: https://github.com/bisman-automations/ha-family/compare/v2.15.0...v2.15.1
[2.15.0]: https://github.com/bisman-automations/ha-family/compare/v2.14.0...v2.15.0
[2.14.0]: https://github.com/bisman-automations/ha-family/compare/v2.13.0...v2.14.0
[2.13.0]: https://github.com/bisman-automations/ha-family/compare/v2.12.0...v2.13.0
[2.12.0]: https://github.com/bisman-automations/ha-family/compare/v2.11.0...v2.12.0
[2.11.0]: https://github.com/bisman-automations/ha-family/compare/v2.10.0...v2.11.0
[2.10.0]: https://github.com/bisman-automations/ha-family/compare/v2.9.0...v2.10.0
[2.9.0]: https://github.com/bisman-automations/ha-family/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/bisman-automations/ha-family/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/bisman-automations/ha-family/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/bisman-automations/ha-family/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/bisman-automations/ha-family/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/bisman-automations/ha-family/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/bisman-automations/ha-family/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/bisman-automations/ha-family/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/bisman-automations/ha-family/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/bisman-automations/ha-family/compare/v1.22.0...v2.0.0
[1.22.0]: https://github.com/bisman-automations/ha-family/compare/v1.21.0...v1.22.0
[1.21.0]: https://github.com/bisman-automations/ha-family/compare/v1.20.0...v1.21.0
[1.20.0]: https://github.com/bisman-automations/ha-family/compare/v1.19.0...v1.20.0
[1.19.0]: https://github.com/bisman-automations/ha-family/compare/v1.18.0...v1.19.0
[1.18.0]: https://github.com/bisman-automations/ha-family/compare/v1.17.0...v1.18.0
[1.17.0]: https://github.com/bisman-automations/ha-family/compare/v1.16.1...v1.17.0
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
