/*
 * Family dashboards: one plain web component, no build step.
 *
 * panel.config.mode picks the dashboard:
 *   "family"  - for everyone, made for a shared touch screen: tap who you are,
 *               mark chores done, spend points on rewards, use the home
 *               controls a parent added.
 *   "parents" - admins: check chores, edit chores, rewards, home controls and
 *               the family, change points, see the history.
 * Data comes from family/state; family/subscribe says when to load it again.
 */

const DOMAIN = "family";
const SECTIONS_KEY = "family-sections";
// On a shared screen, back to everyone after this long without a tap.
const IDLE_MS = 2 * 60 * 1000; // which Family dashboard sections are open, on this screen
// The dashboard the Parents dashboard makes for a shared screen's default.
const DASHBOARD_PATH = "family-dashboard";
const DASHBOARD_TITLE = "Family dashboard";
// The Family dashboard's tabs that Family keeps up to date: Home (everyone),
// then one per family member. Tabs added by hand are kept, after these.
const HOME_VIEW = "family";
const MEMBER_VIEW = "family-member-";

function familyViews(views, members) {
  const old = new Map((views || []).map((v) => [v.path, v]));
  // An existing tab keeps whatever was added to it; only its name follows.
  const tab = (path, title, card) => (old.has(path) ? { ...old.get(path), title } : { title, path, type: "panel", cards: [card] });
  const home = tab(HOME_VIEW, "Home", { type: "custom:family-card" });
  const people = members.map((m) => tab(`${MEMBER_VIEW}${m.id}`, m.emoji ? `${m.emoji} ${m.name}` : m.name, { type: "custom:family-card", member: m.id }));
  const others = (views || []).filter((v) => v.path !== HOME_VIEW && !String(v.path || "").startsWith(MEMBER_VIEW));
  return [home, ...people, ...others];
}

const REPEATS = [
  { id: "daily", label: "Every day" },
  { id: "weekly", label: "Every week" },
  { id: "once", label: "Just once" },
  { id: "after_days", label: "Some days after it's done" },
  { id: "always", label: "Right away, every time it's done" },
  { id: "after_check", label: "Once a parent checks it" },
];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const TURN_EVERY = [
  { id: "time", label: "Each time it's done" },
  { id: "day", label: "Each day" },
  { id: "week", label: "Each week (from Monday)" },
];
const timeText = (hhmm) => {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map(Number);
  const d = new Date(2000, 0, 1, h, m);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
};
// "Tue, Thu", "8:00 AM to 9:00 AM": when a chore shows, for the Parents list.
const whenShown = (c) => {
  const days = c.days?.length ? c.days.map((d) => DAYS[d]).join(", ") : "";
  const hours = c.from_time && c.until_time ? `${timeText(c.from_time)} to ${timeText(c.until_time)}` : c.from_time ? `from ${timeText(c.from_time)}` : c.until_time ? `until ${timeText(c.until_time)}` : "";
  return [days, hours].filter(Boolean).join(" ");
};
const repeatText = (c) =>
  c.repeat === "after_days" ? `Back ${c.repeat_days || 1} ${c.repeat_days === 1 ? "day" : "days"} after it's done` : REPEATS.find((r) => r.id === c.repeat)?.label || "";

// Home controls: how each kind of entity is grouped and drawn.
const DOMAIN_LABELS = {
  scene: "Scenes", script: "Scripts", button: "Buttons", input_button: "Buttons",
  light: "Lights", switch: "Switches", input_boolean: "Switches", fan: "Fans",
  humidifier: "Humidifiers", siren: "Sirens", cover: "Blinds, curtains and doors", valve: "Valves",
  lock: "Locks", media_player: "Speakers and TVs", climate: "Thermostats", water_heater: "Water heaters",
  sensor: "Sensors", binary_sensor: "Sensors", weather: "Weather", person: "People",
  input_number: "Numbers", number: "Numbers", input_select: "Choices", select: "Choices",
};
const DOMAIN_ICONS = {
  scene: "mdi:palette", script: "mdi:script-text-play", button: "mdi:gesture-tap-button", input_button: "mdi:gesture-tap-button",
  light: "mdi:lightbulb", switch: "mdi:toggle-switch-variant", input_boolean: "mdi:toggle-switch-variant", fan: "mdi:fan",
  humidifier: "mdi:air-humidifier", siren: "mdi:bullhorn", cover: "mdi:window-shutter", valve: "mdi:valve",
  lock: "mdi:lock", media_player: "mdi:speaker", climate: "mdi:thermostat", water_heater: "mdi:water-boiler",
  sensor: "mdi:eye", binary_sensor: "mdi:checkbox-marked-circle-outline", weather: "mdi:weather-partly-cloudy", person: "mdi:account",
  input_number: "mdi:ray-vertex", number: "mdi:ray-vertex", input_select: "mdi:format-list-bulleted", select: "mdi:format-list-bulleted",
};
const LIMITS = [
  { id: "", label: "Any time" },
  { id: "daily", label: "Once a day each" },
  { id: "weekly", label: "Once a week each" },
];
const LIMIT_TEXT = { daily: "Once a day", weekly: "Once a week" };
const AGAIN = { daily: "Again tomorrow", weekly: "Again next week" };
const AUTO_CHECKS = [
  { id: "", label: "Never: a parent checks every chore" },
  { id: "day", label: "After a day" },
  { id: "week", label: "After a week" },
];
const KIND_TEXT = {
  toggle: "Tap to turn on or off", run: "Tap to start", open: "Tap to open or close",
  lock: "Tap to lock or unlock", media: "Tap to play or pause", view: "Shown only",
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const whenText = (iso) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return `Today ${time}`;
  const yesterday = new Date(today.getTime() - 86400000);
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday ${time}`;
  return `${d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })} ${time}`;
};

const pts = (n) => `${n} ${Math.abs(n) === 1 ? "point" : "points"}`;
const MEALS = [["breakfast", "Breakfast"], ["lunch", "Lunch"], ["dinner", "Dinner"]];
const WEEKDAYS_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
// An ISO date (YYYY-MM-DD) as "Mon 9", "Today" or "Tomorrow".
const dayText = (iso, index) => {
  if (index === 0) return "Today";
  if (index === 1) return "Tomorrow";
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
};
// When a calendar event starts: "All day", or its time.
const eventTime = (e) => (e.all_day ? "All day" : new Date(e.start).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
const money = (points, m) => {
  if (!m?.value) return "";
  const amount = points * m.value;
  return `${m.currency || ""}${amount.toFixed(amount % 1 ? 2 : 0)}`;
};
const signed = (n) => (n > 0 ? `+${n}` : `${n}`);
// The Family dashboard's sections and their usual order (model.SECTIONS).
const SECTIONS = [
  ["going", "Going for"],
  ["chores", "My chores"],
  ["routines", "Routines"],
  ["grabs", "Up for grabs"],
  ["notes", "Notes"],
  ["today", "Today"],
  ["meals", "Meals"],
  ["done", "Done today"],
  ["rewards", "Rewards"],
  ["home", "Home"],
  ["lately", "Lately"],
];
// Like model.section_order: known sections once each, missing ones at the end.
const sectionOrder = (order) => {
  const keys = SECTIONS.map(([k]) => k);
  const seen = [...new Set(order || [])].filter((k) => keys.includes(k));
  return [...seen, ...keys.filter((k) => !seen.includes(k))];
};
// "Alex", "Alex and Sam", "Alex, Sam and Riley".
const namesText = (names) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);
// A reward's points shared as evenly as each one's points allow, like
// model.split_points: [[id, points], ...] in, {id: share} or null out.
function splitPoints(cost, balances) {
  const left = Object.fromEntries(balances.map(([id, p]) => [id, Math.max(0, p)]));
  const shares = Object.fromEntries(balances.map(([id]) => [id, 0]));
  let remaining = Math.max(0, cost);
  while (remaining > 0) {
    const able = balances.map(([id]) => id).filter((id) => left[id] > 0);
    if (!able.length) return null;
    const each = Math.floor(remaining / able.length);
    const extra = remaining % able.length;
    able.forEach((id, i) => {
      const give = Math.min(left[id], each + (i < extra ? 1 : 0));
      shares[id] += give;
      left[id] -= give;
      remaining -= give;
    });
  }
  return shares;
}
// A timed event that's already over.
const eventOver = (e, now = Date.now()) => !e.all_day && !!e.end && new Date(e.end).getTime() <= now;

const STYLES = `
  :host {
    display: block; min-height: 100%;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, sans-serif));
    --fam-card: var(--card-background-color, #fff);
    --fam-divider: var(--divider-color, #e0e0e0);
    --fam-muted: var(--secondary-text-color, #727272);
    --fam-radius: var(--ha-card-border-radius, 16px);
    --fam-good: var(--success-color, #43a047);
    --fam-bad: var(--error-color, #db4437);
  }
  .toolbar {
    display: flex; align-items: center; gap: 4px;
    height: var(--header-height, 56px); padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    position: sticky; top: 0; z-index: 3;
  }
  .title { font-size: 20px; font-weight: 400; margin-left: 4px; }
  main { max-width: 1400px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
  h2 { font-size: 22px; font-weight: 500; margin: 24px 0 12px; }
  h2:first-child { margin-top: 4px; }
  .muted { color: var(--fam-muted); }
  .empty { color: var(--fam-muted); padding: 16px 0; font-size: 16px; line-height: 1.5; }
  .error { color: var(--fam-bad); margin: 8px 0; }

  /* Family: who's who */
  .people { display: flex; gap: 14px; overflow-x: auto; padding: 4px 2px 8px; }
  .person {
    flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; gap: 6px;
    min-width: 108px; padding: 12px 10px; border-radius: var(--fam-radius); cursor: pointer;
    background: var(--fam-card); border: 3px solid transparent; font: inherit; color: inherit;
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12));
  }
  .person[aria-pressed="true"] { border-color: var(--c); }
  .avatar {
    width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center;
    background: var(--c); color: #fff; font-size: 34px; font-weight: 600; overflow: hidden;
  }
  .avatar img { width: 100%; height: 100%; object-fit: cover; }
  .avatar.small { width: 30px; height: 30px; font-size: 15px; }
  .person .name { font-size: 17px; font-weight: 500; }
  .person .points { font-size: 15px; color: var(--fam-muted); }
  .person .points b { color: var(--primary-text-color); font-size: 18px; }

  /* Tiles: chores and rewards */
  .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 14px; }
  .tile {
    display: flex; flex-direction: column; align-items: flex-start; gap: 6px; text-align: left;
    padding: 16px; min-height: 120px; border-radius: var(--fam-radius); cursor: pointer;
    background: var(--fam-card); color: inherit; font: inherit; border: 1px solid var(--fam-divider);
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12));
  }
  .tile:disabled { opacity: .45; cursor: default; }
  .tile.chore { position: relative; cursor: default; padding-right: 64px; }
  .tile.chore .check { position: absolute; right: 12px; bottom: 12px; width: 46px; height: 46px; border-radius: 50%; border: 3px solid var(--primary-color); background: var(--card-background-color); cursor: pointer; display: grid; place-items: center; padding: 0; }
  .tile.chore .check svg { width: 28px; height: 28px; fill: none; stroke: var(--primary-color); stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; opacity: .25; }
  .tile.chore .check:hover svg, .tile.chore .check:focus-visible svg { opacity: 1; }
  .tile.chore .check:active { background: var(--primary-color); }
  .tile.chore .check:active svg { stroke: var(--text-primary-color, #fff); opacity: 1; }
  .tile .emoji { font-size: 34px; line-height: 1; }
  .tile .label { font-size: 18px; font-weight: 500; }
  .tile .worth { font-size: 16px; font-weight: 600; color: var(--primary-color); margin-top: auto; }
  .tile .sub { font-size: 13px; color: var(--fam-muted); }
  .who { display: flex; gap: 4px; }
  .tiles > [hidden], .feed > li[hidden], .more[hidden], .field[hidden] { display: none !important; }
  .tile.done { cursor: default; opacity: .75; min-height: 96px; background: transparent; box-shadow: none; }
  .tile.done .tick { font-size: 26px; line-height: 1; color: var(--fam-good); font-weight: 700; }
  .tile.done .worth { color: var(--fam-good); }
  .bar { display: block; width: 100%; height: 8px; border-radius: 4px; background: var(--fam-divider); overflow: hidden; }
  .bar > span { display: block; height: 100%; background: var(--primary-color); border-radius: 4px; }
  .tile:disabled .bar { opacity: 1; }
  .streak { font-size: 15px; font-weight: 600; }
  .pills { display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; }
  .pill { font-size: 14px; font-weight: 600; padding: 3px 10px; border-radius: 999px; background: color-mix(in srgb, var(--c, var(--primary-color)) 16%, transparent); color: var(--primary-text-color); }
  .pill.done { background: color-mix(in srgb, var(--success-color, #2e7d32) 22%, transparent); }
  .pill.missed { background: color-mix(in srgb, var(--error-color, #c62828) 14%, transparent); font-weight: 500; }
  .celebrate { position: fixed; inset: 0; z-index: 20; background: rgba(0, 0, 0, .45); overflow: hidden; display: flex; align-items: center; justify-content: center; cursor: pointer; }
  .celebrate .cheer { position: relative; color: #fff; font-size: clamp(26px, 4vw, 44px); font-weight: 600; text-align: center; padding: 0 24px; text-shadow: 0 2px 8px rgba(0, 0, 0, .4); animation: cheer .5s ease-out; }
  .celebrate .confetti { position: absolute; top: -60px; animation: fall 3.2s ease-in forwards; }
  @keyframes fall { to { transform: translateY(110vh) rotate(540deg); } }
  @keyframes cheer { from { transform: scale(.6); opacity: 0; } to { transform: scale(1); opacity: 1; } }
  @media (prefers-reduced-motion: reduce) { .celebrate .confetti { display: none; } .celebrate .cheer { animation: none; } }
  .going-tile { gap: 6px; }
  .going-tile.won { justify-content: center; }
  .goal-mini { display: flex; align-items: center; gap: 6px; width: 100%; font-size: 14px; }
  .goal-card {
    display: flex; align-items: center; gap: 16px; width: 100%; margin: 8px 0 4px; padding: 14px 18px;
    border-radius: var(--fam-radius); border: 2px solid var(--primary-color); background: var(--fam-card);
    color: inherit; font: inherit; text-align: left; cursor: pointer; box-sizing: border-box;
  }
  .goal-card .emoji { font-size: 38px; line-height: 1; }
  .goal-card .goal-text { display: grid; gap: 6px; flex: 1; }
  .goal-card .label { font-size: 18px; font-weight: 500; }
  .goal-card .sub { font-size: 14px; color: var(--fam-muted); }
  .tile.short { opacity: .6; }
  .tile.goal { border-color: var(--primary-color); box-shadow: inset 0 0 0 2px var(--primary-color); opacity: 1; }
  .goal-tag { color: var(--primary-color) !important; font-weight: 600; }
  .streak-line { font-size: 17px; font-weight: 500; color: var(--fam-muted); margin-left: 8px; }
  @media (max-width: 500px) {
    .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .tile { padding: 12px; min-height: 104px; }
    .tile .label { font-size: 16px; }
  }
  h2.sec { margin: 20px 0 8px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .sec-extra { font-size: 15px; }
  .tile.event.over { opacity: .55; }
  .tile.event.over .label { text-decoration: line-through; }
  .over-tag { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; padding: 1px 6px; border-radius: 8px; background: var(--fam-divider, var(--divider-color)); color: var(--primary-text-color); margin-left: 4px; }
  .tile.event.empty-day { justify-content: center; color: var(--fam-muted); }
  .sheet.wide { width: min(900px, 100%); max-height: calc(100vh - 32px); overflow: auto; text-align: left; }
  .sheet.wide h3, .sheet.wide .actions { text-align: center; }
  ul.days { list-style: none; margin: 0 0 16px; padding: 0; display: grid; gap: 14px; }
  ul.days h4 { margin: 0 0 6px; font-size: 18px; font-weight: 500; }
  ul.days .nothing { margin: 0; font-size: 15px; }
  ul.days .tile.event { min-height: 0; }
  .sheet .split { font-size: 18px; color: var(--primary-text-color); margin-top: 12px; }
  .sheet .split.ready { font-weight: 500; }
  .avatars { display: inline-flex; }
  .avatars > * + * { margin-left: -8px; }
  .sec-toggle {
    font: inherit; font-size: 22px; font-weight: 500; color: inherit; background: none; border: 0;
    padding: 4px 8px 4px 0; min-height: 48px; cursor: pointer; display: inline-flex; align-items: center; gap: 12px;
  }
  .chev {
    width: 10px; height: 10px; border-right: 3px solid currentColor; border-bottom: 3px solid currentColor;
    transform: rotate(45deg); margin: 0 4px 5px 6px; transition: transform .15s;
  }
  .sec-toggle[aria-expanded="false"] .chev { transform: rotate(-45deg); margin-bottom: 0; }
  .count {
    font-size: 15px; font-weight: 600; color: var(--fam-muted); border: 1px solid var(--fam-divider);
    background: var(--fam-card); border-radius: 12px; padding: 1px 10px;
  }
  .more {
    display: block; margin: 14px auto 0; font: inherit; font-size: 17px; font-weight: 600; min-height: 48px;
    padding: 0 28px; border-radius: 24px; border: 1px solid var(--fam-divider); background: var(--fam-card);
    color: var(--primary-color); cursor: pointer;
  }
  .tile.note { position: relative; cursor: default; min-height: 96px; border-left: 6px solid var(--c, var(--primary-color)); background: color-mix(in srgb, var(--c, var(--primary-color)) 8%, var(--card-background-color, #fff)); }
  .tile.note .note-text { font-size: 17px; line-height: 1.35; padding-right: 26px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .tile.note .sub { display: flex; align-items: center; gap: 6px; margin-top: auto; }
  .note-x { position: absolute; top: 8px; right: 8px; width: 32px; height: 32px; border-radius: 50%; border: none; background: transparent; color: var(--fam-muted); font-size: 16px; cursor: pointer; }
  .note-x:hover { background: var(--divider-color); }
  .tile.add-note { min-height: 96px; border-style: dashed; background: transparent; box-shadow: none; align-items: center; justify-content: center; text-align: center; }
  .tile.event { cursor: default; min-height: 90px; border-left: 6px solid var(--c, var(--divider-color)); }
  .tile.event .when { font-size: 14px; font-weight: 600; color: var(--primary-color); }
  .tile.meal { cursor: default; min-height: 90px; gap: 4px; }
  .tile.meal .meal-line { font-size: 16px; }
  .tile.meal .meal-line small { display: block; font-size: 12px; color: var(--fam-muted); text-transform: uppercase; letter-spacing: .04em; }
  .small-people { flex-wrap: wrap; }
  .person.pick { cursor: pointer; flex-direction: row; gap: 8px; padding: 8px 12px; min-width: 0; }
  .person.pick input { margin: 0; }
  .sheet textarea { width: 100%; box-sizing: border-box; font: inherit; font-size: 17px; padding: 10px; border-radius: 10px; border: 1px solid var(--divider-color); background: var(--card-background-color, #fff); color: var(--primary-text-color); }
  .meal-row { display: grid; grid-template-columns: 150px repeat(3, minmax(0, 1fr)) auto; gap: 10px; align-items: end; padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
  .meal-row .meal-day { align-self: center; }
  .meal-row .field { min-width: 0; }
  .meal-row input { width: 100%; min-width: 0; box-sizing: border-box; }
  .money { color: var(--fam-muted); font-weight: 400; }
  @media (max-width: 700px) {
    .meal-row { grid-template-columns: 1fr 1fr; }
    .meal-row .meal-day { grid-column: 1 / -1; }
  }
  .tile.control { min-height: 110px; }
  .tile.control .icon { --mdc-icon-size: 34px; color: var(--fam-muted); line-height: 1; }
  .tile.control.on { border-color: var(--primary-color); box-shadow: inset 0 0 0 2px var(--primary-color); }
  .tile.control.on .icon { color: var(--state-active-color, var(--primary-color)); }
  .tile.control .state { font-size: 15px; color: var(--fam-muted); }
  .tile.control.view { cursor: default; }
  .tile.control.view .state { font-size: 22px; font-weight: 600; color: var(--primary-text-color); }
  .tile.control .do { font-size: 15px; font-weight: 600; color: var(--primary-color); margin-top: auto; }
  select[size] { min-height: 200px; width: 100%; }
  button:focus-visible, .tile:focus-visible, .person:focus-visible { outline: 3px solid var(--primary-color); outline-offset: 2px; }

  /* Sheet: confirm and pick who */
  .sheet-bg { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: grid; place-items: center; z-index: 5; padding: 16px; }
  .sheet {
    background: var(--fam-card); border-radius: 20px; padding: 24px; width: min(520px, 100%);
    box-sizing: border-box; text-align: center; box-shadow: 0 10px 40px rgba(0,0,0,.3);
  }
  .sheet h3 { margin: 0 0 8px; font-size: 24px; font-weight: 500; }
  .sheet p { margin: 0 0 18px; font-size: 17px; color: var(--fam-muted); }
  .sheet .people { justify-content: center; flex-wrap: wrap; }
  .sheet .actions { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
  .big { font: inherit; font-size: 18px; min-height: 56px; padding: 0 28px; border-radius: 28px; cursor: pointer; border: 1px solid var(--fam-divider); background: transparent; color: inherit; }
  .big:disabled, .btn:disabled { opacity: .45; cursor: default; }
  .big.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .toast {
    position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 6;
    background: var(--fam-good); color: #fff; padding: 14px 24px; border-radius: 28px;
    font-size: 18px; box-shadow: 0 4px 16px rgba(0,0,0,.25);
    width: max-content; max-width: calc(100vw - 32px); box-sizing: border-box; text-align: center;
  }
  .toast.bad { background: var(--fam-bad); }
  .toast { display: flex; align-items: center; gap: 16px; }
  .toast .undo {
    font: inherit; font-size: 17px; font-weight: 600; color: #fff; background: rgba(255,255,255,.2);
    border: 2px solid #fff; border-radius: 22px; min-height: 44px; padding: 0 20px; cursor: pointer;
  }

  .feed { list-style: none; margin: 0; padding: 0; }
  .feed li { display: flex; gap: 12px; align-items: center; padding: 10px 0; border-top: 1px solid var(--fam-divider); font-size: 15px; }
  .feed li:first-child { border-top: 0; }
  .feed .what { flex: 1; }
  .feed .amount { font-weight: 600; white-space: nowrap; }
  .feed .amount.plus { color: var(--fam-good); }
  .feed .amount.minus { color: var(--fam-muted); }
  .feed .amount.gone { text-decoration: line-through; color: var(--fam-muted); }

  /* Parents */
  .tabs { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; margin-bottom: 8px; }
  .tab { border: 1px solid var(--fam-divider); background: var(--fam-card); color: inherit; font: inherit; border-radius: 999px; padding: 8px 16px; cursor: pointer; white-space: nowrap; }
  .tab[aria-selected="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .card { background: var(--fam-card); border: 1px solid var(--fam-divider); border-radius: var(--fam-radius); padding: 16px; margin-bottom: 16px; }
  .card > h2[data-fold] { cursor: pointer; display: flex; align-items: center; gap: 10px; }
  .card > h2[data-fold]::before { content: ""; width: 9px; height: 9px; border-right: 2.5px solid currentColor; border-bottom: 2.5px solid currentColor; transform: rotate(45deg); margin: 0 4px 4px 2px; transition: transform .15s; flex: none; }
  .card.folded > h2[data-fold]::before { transform: rotate(-45deg); margin-bottom: 0; }
  .card.folded > :not(h2) { display: none; }
  .items li.skipped .item-name { opacity: 0.5; text-decoration: line-through; }
  .chip.leave-out { color: var(--error-color, #db4437); }
  [hidden] { display: none !important; }
  .routine-tile { text-align: left; }
  .routine-people { display: flex; flex-wrap: wrap; gap: 4px; }
  .routine-people .pill { font-size: 0.8em; padding: 2px 8px; border-radius: 999px; background: var(--secondary-background-color, #eee); }
  .routine-people .pill.won { background: rgba(67, 160, 71, 0.18); }
  textarea[name="steps"] { font: inherit; line-height: 1.5; }
  ul.steps { list-style: none; padding: 0; margin: 12px 0; display: grid; gap: 8px; max-height: 55vh; overflow: auto; }
  .step { width: 100%; display: flex; align-items: center; gap: 12px; padding: 14px; font: inherit; font-size: 1.1em; text-align: left; border-radius: 14px; border: 1px solid var(--divider-color, #ddd); background: var(--card-background-color, #fff); color: var(--primary-text-color); cursor: pointer; }
  .step .box { width: 28px; height: 28px; flex: none; display: grid; place-items: center; border-radius: 8px; border: 2px solid var(--primary-color); color: #fff; font-weight: 700; }
  .step.done { opacity: 0.75; }
  .step.done .box { background: var(--primary-color); }
  .step.done span:last-child { text-decoration: line-through; }
  .goal-status .bar { display: block; margin: 6px 0 4px; }
  .quick-buttons { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
  details.left-out { margin-top: 8px; }
  details.left-out > summary { cursor: pointer; color: var(--secondary-text-color); padding: 6px 0; }
  .matrix-wrap { overflow-x: auto; }
  .matrix table { border-collapse: collapse; }
  .matrix th, .matrix td { padding: 8px 6px; min-width: 64px; border-top: 1px solid var(--fam-divider); text-align: center; font-weight: 400; }
  .matrix tr:first-child th { border-top: 0; font-size: 14px; vertical-align: bottom; }
  .matrix tr:first-child th span { display: block; margin-top: 4px; }
  .matrix th.chore { text-align: left; font-weight: 500; position: sticky; left: 0; z-index: 1; background: var(--card-background-color); min-width: 140px; max-width: 260px; }
  .matrix th.chore small, .matrix .group small { display: block; font-weight: 400; color: var(--fam-muted); font-size: 13px; }
  .matrix .group th { text-align: left; font-weight: 600; padding-top: 16px; background: var(--fam-divider, var(--divider-color)); }
  .matrix .group th { position: sticky; left: 0; }
  .matrix .mark { font-size: 18px; }
  .matrix .mark.own { color: var(--primary-color); font-weight: 600; }
  .matrix .mark.turn { color: var(--primary-color); opacity: .6; }
  .matrix .mark.grab { color: var(--fam-muted); }
  .matrix .totals th { text-align: left; font-weight: 500; }
  .matrix .totals td { font-weight: 600; }
  .rows { list-style: none; margin: 0; padding: 0; }
  .rows li { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; padding: 12px 0; border-top: 1px solid var(--fam-divider); }
  .rows li:first-child { border-top: 0; }
  .rows .grow { flex: 1; min-width: 180px; }
  .rows .grow small { display: block; color: var(--fam-muted); margin-top: 2px; }
  .btn { font: inherit; font-size: 14px; min-height: 38px; padding: 0 14px; border-radius: 19px; cursor: pointer; border: 1px solid var(--fam-divider); background: transparent; color: inherit; }
  .btn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .btn.good { border-color: var(--fam-good); color: var(--fam-good); }
  .btn.bad { border-color: var(--fam-bad); color: var(--fam-bad); }
  form.edit { display: grid; gap: 12px; }
  .field { display: grid; gap: 4px; }
  .field > span { font-size: 14px; font-weight: 500; }
  .field small { color: var(--fam-muted); }
  .inline { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
  .check { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; }
  input[type="text"], input[type="number"], input[type="time"], select {
    font: inherit; font-size: 15px; padding: 8px 10px; min-height: 40px; box-sizing: border-box;
    border-radius: 8px; border: 1px solid var(--fam-divider); background: var(--fam-card); color: inherit; max-width: 100%;
  }
  /* Who can get a reward: a dropdown of the family. No Everyone row. */
  .eligible { display: grid; gap: 4px; max-width: 420px; }
  .eligible-btn {
    font: inherit; font-size: 15px; line-height: 1.3; min-height: 40px; padding: 8px 36px 8px 10px;
    box-sizing: border-box; width: 100%; text-align: left; cursor: pointer; white-space: normal;
    border-radius: 8px; border: 1px solid var(--fam-divider); background: var(--fam-card); color: inherit;
    position: relative;
  }
  .eligible-btn::after {
    content: ""; position: absolute; right: 14px; top: 50%; width: 8px; height: 8px; margin-top: -6px;
    border-right: 2px solid currentColor; border-bottom: 2px solid currentColor; transform: rotate(45deg);
  }
  .eligible-btn[aria-expanded="true"]::after { margin-top: -2px; transform: rotate(225deg); }
  .eligible-menu {
    display: grid; padding: 4px; border-radius: 8px; border: 1px solid var(--fam-divider);
    background: var(--fam-card); box-shadow: 0 8px 24px rgba(0,0,0,.16);
  }
  .eligible-menu[hidden] { display: none !important; }
  .eligible-option {
    display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 4px 10px;
    border-radius: 8px; cursor: pointer; font-size: 16px;
  }
  .eligible-option:hover, .eligible-option:focus-within { background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
  .eligible-option input { width: 20px; height: 20px; margin: 0; accent-color: var(--primary-color); }
  .field small.eligible-warn { color: var(--fam-bad); font-weight: 600; }
  .form-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .items { list-style: none; margin: 4px 0 0; padding: 0; max-width: 980px; }
  .items li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--fam-divider); flex-wrap: wrap; }
  .items .item-name { flex: 1 1 200px; }
  .items .item-emoji { width: 3em; text-align: center; font-size: 20px; padding: 4px; }
  .items .item-who { display: flex; flex-wrap: wrap; gap: 4px 10px; }
  .items .chip { display: inline-flex; align-items: center; gap: 4px; font-size: 14px; white-space: nowrap; }
  .items .chip input { width: auto; margin: 0; }
  .items li:first-child { border-top: 0; }
  .items input { width: 100px; }
  .penalty { display: inline-flex; gap: 6px; align-items: center; }
  .penalty input { width: 72px; }
  .penalty-setting { margin-top: 12px; align-items: flex-end; }
  .badge { display: inline-block; min-width: 20px; padding: 0 6px; border-radius: 10px; background: var(--fam-bad); color: #fff; font-size: 12px; line-height: 20px; text-align: center; margin-left: 6px; }
`;

class FamilyPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = "";
    this._member = null; // who's using the shared screen
    this._sheet = null; // {type: "chore"|"reward", item, member?}
    this._tab = "review";
    this._edit = null; // {collection, item}
    this._choices = null;
    this._busy = false;
    try {
      this._sections = JSON.parse(localStorage.getItem(SECTIONS_KEY) || "{}") || {};
    } catch (_err) {
      this._sections = {};
    }
  }

  get _mode() {
    return this._panel?.config?.mode === "parents" ? "parents" : "family";
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._build();
    if (first) {
      this._load();
      this._subscribe();
    } else if (this._mode === "family" && this._data?.controls?.length) {
      // Home controls follow their entities live.
      const seen = this._seenStates || {};
      if (this._data.controls.some((c) => hass.states[c.entity_id] !== seen[c.entity_id])) this._refreshControls();
    }
    this._menu();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._menu();
  }

  set panel(panel) {
    this._panel = panel;
    if (this._built) this._render();
  }

  disconnectedCallback() {
    clearInterval(this._idleTimer);
    this._idleTimer = null;
    if (this._unsub) {
      this._unsub.then((unsub) => unsub()).catch(() => {});
      this._unsub = null;
    }
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._subscribe();
    this._watchIdle();
  }

  // The next person to walk up to the shared screen shouldn't land on the
  // last kid's page: after a while with no taps, go back to everyone, with
  // each section back to its first row (closed ones stay closed).
  _watchIdle() {
    if (this._idleTimer) return;
    this._lastTouch = Date.now();
    this._idleTimer = setInterval(() => this._idleCheck(), 15000);
  }

  // Whose page this screen goes back to: the card's own member, else the login's.
  _homeMember() {
    if (this._pinned && this._data?.members.some((m) => m.id === this._pinned)) return this._pinned;
    return this._data?.me ?? null;
  }

  _idleCheck() {
    if (this._mode === "family" && this._data && this._overCount() !== this._over) {
      this._over = this._overCount();
      if (this._sheet?.type === "days") this._renderOverlay();
      else if (!this._sheet && !this._busy) this._render();
    }
    if (this._mode !== "family" || !this._data || this._sheet || this._busy) return;
    if (Date.now() - this._lastTouch < IDLE_MS) return;
    const home = this._homeMember();
    const opened = Object.values(this._sections).includes("all");
    if (this._member === home && !opened) return;
    this._member = home;
    for (const [key, mode] of Object.entries(this._sections)) if (mode === "all") this._sections[key] = "first";
    try {
      localStorage.setItem(SECTIONS_KEY, JSON.stringify(this._sections));
    } catch (_err) {
      // private browsing: just for now
    }
    this._render();
  }

  _subscribe() {
    if (this._unsub || !this._hass?.connection) return;
    this._unsub = this._hass.connection.subscribeMessage(() => {
      clearTimeout(this._reload);
      this._reload = setTimeout(() => this._load(), 300);
    }, { type: `${DOMAIN}/subscribe` });
  }

  async _load() {
    try {
      this._data = await this._hass.callWS({ type: `${DOMAIN}/state` });
      this._error = "";
      // Someone logged in as a family member sees their own page.
      if (this._member === null && this._mode === "family") this._member = this._homeMember();
      if (this._member && !this._data.members.some((m) => m.id === this._member)) this._member = this._homeMember();
      if (this._mode === "parents" && this._hasDashboard === undefined) {
        this._hasDashboard = null;
        this._ws({ type: "lovelace/dashboards/list" })
          .then((list) => {
            this._hasDashboard = list.some((d) => d.url_path === DASHBOARD_PATH);
            this._render();
          })
          .catch(() => {
            this._hasDashboard = false;
          });
      }
      if (this._mode === "parents" && !this._choices) {
        this._choices = await this._hass.callWS({ type: `${DOMAIN}/choices` });
      }
    } catch (err) {
      this._error = err?.message || String(err);
    }
    this._render();
  }

  _build() {
    if (this._built) return;
    this._built = true;
    // As a card, the dashboard around it has its own header.
    const toolbar = this._card ? "" : `<div class="toolbar"><div class="menu"></div><div class="title"></div></div>`;
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>${toolbar}
      <main></main><div class="overlay"></div>`;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("submit", (ev) => this._onSubmit(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
    this.shadowRoot.addEventListener("input", (ev) => this._onInput(ev));
    this.shadowRoot.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") this._closeEligible();
      // A folding heading opens and closes with Enter or Space too.
      const head = ev.target?.closest?.("[data-fold]");
      if (head && (ev.key === "Enter" || ev.key === " ")) {
        ev.preventDefault();
        this._toggleFold(head.dataset.fold);
      }
    });
    this.shadowRoot.addEventListener("pointerdown", () => (this._lastTouch = Date.now()), true);
    this._watchIdle();
    // How many tiles fit in a row changes with the screen's width.
    if (window.ResizeObserver) {
      this._resize = new ResizeObserver(() => this._fit());
      this._resize.observe(this.shadowRoot.querySelector("main"));
    }
  }

  _menu() {
    if (!this._built) return;
    const menu = this.shadowRoot.querySelector(".menu");
    if (!menu) return;
    let button = menu.querySelector("ha-menu-button");
    if (!button) {
      button = document.createElement("ha-menu-button");
      menu.appendChild(button);
    }
    button.hass = this._hass;
    button.narrow = this._narrow;
  }

  // ------------------------------------------------------------------ helpers

  _memberById(id) {
    return this._data?.members.find((m) => m.id === id);
  }

  _avatar(m, small = false) {
    const inner = m.picture
      ? `<img src="${esc(this._hass.hassUrl ? this._hass.hassUrl(m.picture) : m.picture)}" alt="">`
      : esc(m.emoji || m.name.slice(0, 1).toUpperCase());
    return `<span class="avatar${small ? " small" : ""}" style="--c:${esc(m.color)}">${inner}</span>`;
  }

  // All of someone's own chores done: confetti and a cheer for a few seconds.
  _celebrate(member) {
    const old = this.shadowRoot.querySelector(".celebrate");
    if (old) old.remove();
    const bits = ["🎉", "🥳", "⭐", "🎊", "✨"];
    const pieces = Array.from({ length: 28 }, (_, i) => {
      const left = (i * 37) % 100;
      const delay = ((i * 13) % 10) / 10;
      const size = 28 + ((i * 7) % 20);
      return `<span class="confetti" style="left:${left}%;animation-delay:${delay}s;font-size:${size}px">${bits[i % bits.length]}</span>`;
    }).join("");
    const el = document.createElement("div");
    el.className = "celebrate";
    el.setAttribute("role", "status");
    el.innerHTML = `${pieces}<div class="cheer">Yay, ${esc(member.name)}! You did all your chores today.</div>`;
    el.addEventListener("click", () => el.remove());
    this.shadowRoot.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  // On the people strip: how many of their own chores are left today.
  _todoLine(m) {
    const own = m.own_today || {};
    if (!own.total) return "";
    const doneCount = own.total - own.left;
    const all = own.done || !own.left;
    // Left, but too late today: missed rather than still to do.
    const missed = all ? 0 : Math.min(own.missed || 0, own.left);
    return `<span class="pills"><span class="pill${all ? " done" : ""}" title="${all ? "All done today" : `${own.left} to do`}">✓ ${all ? own.total : doneCount}/${own.total}</span>${missed ? `<span class="pill missed">${missed} missed</span>` : ""}</span>`;
  }

  // A card set to one family member shows only their page.
  _pinnedMember() {
    return this._pinned ? this._memberById(this._pinned) : null;
  }

  _people(members, attr, selected) {
    return `<div class="people" role="group">${members
      .map((m) => `<button class="person" style="--c:${esc(m.color)}" ${attr}="${esc(m.id)}" aria-pressed="${Array.isArray(selected) ? selected.includes(m.id) : m.id === selected}">
          ${this._avatar(m)}<span class="name">${esc(m.name)}</span>
          <span class="points"><b>${m.points}</b> ${m.points === 1 ? "point" : "points"}${this._data?.money ? `<small class="money"> · ${esc(money(m.points, this._data.money))}</small>` : ""}</span>
          ${m.streak >= 2 ? `<span class="streak" title="${m.streak} days in a row">🔥 ${m.streak}</span>` : ""}${attr === "data-member" ? this._todoLine(m) : ""}${this._goalBar(m)}</button>`)
      .join("")}</div>`;
  }

  // The reward someone's saving for, if it's still there and still for them.
  _goal(m) {
    const goal = m?.goal ? this._data?.rewards.find((r) => r.id === m.goal) : null;
    if (!goal || !this._canGet(goal, m.id)) return null;
    return goal;
  }

  // model.reward_for: no members (null) is everyone, [] is nobody.
  _canGet(reward, memberId) {
    if (!reward || !memberId) return false;
    if (reward.members == null) return true;
    return reward.members.includes(memberId);
  }

  // model.reward_visible: someone's page shows theirs and everyone's;
  // everyone's page shows only rewards for everyone.
  _visibleRewards(member) {
    return (this._data?.rewards || []).filter((r) => {
      if (r.members == null) return true;
      if (!member) return false;
      return r.members.includes(member.id);
    });
  }

  // People a parent picked for this reward. Null members: the whole family.
  _eligibleMembers(reward) {
    const members = this._data?.members || [];
    if (reward.members == null) return members;
    const allowed = new Set(reward.members);
    return members.filter((m) => allowed.has(m.id));
  }

  // "Everyone", "Alex, Sam", or "nobody" (the reward is unavailable).
  _forLabel(members) {
    if (members == null) return "Everyone";
    const names = members.map((id) => this._memberById(id)?.name).filter(Boolean);
    return names.length ? names.join(", ") : "nobody";
  }

  _bar(have, need) {
    return `<span class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${need}" aria-valuenow="${Math.min(have, need)}"><span style="width:${Math.min(100, Math.round((100 * have) / Math.max(1, need)))}%"></span></span>`;
  }

  _goalBar(m) {
    const goal = this._goal(m);
    if (!goal) return "";
    return `<span class="goal-mini" title="Saving for ${esc(goal.name)}">${goal.emoji ? esc(goal.emoji) : "🎯"} ${this._bar(m.points, goal.points)}</span>`;
  }

  _rewardSub(r) {
    if (r.kind === "tv_time") return `${r.minutes} min of TV${r.tv_name ? ` · ${r.tv_name}` : ""}`;
    if (r.kind === "music_time") return `${r.minutes} min of music${r.speaker_name ? ` · ${r.speaker_name}` : ""}`;
    return "";
  }

  // Parents list: "5 points · 15 min on Family Room TV · For: Alex, Sam".
  _rewardLine(r) {
    const bits = [pts(r.points)];
    if (r.limit) {
      const label = LIMITS.find((l) => l.id === r.limit)?.label;
      if (label) bits.push(label.toLowerCase());
    }
    if (r.kind === "tv_time") bits.push(`${r.minutes} min on ${r.tv_name || "a TV that's gone"}${r.whole_home ? " and the whole home" : ""}`);
    else if (r.kind === "music_time") bits.push(`${r.minutes} min of music on ${r.speaker_name || "a speaker that's gone"}${r.whole_home ? " and the whole home" : ""}`);
    else bits.push("handed out by a parent");
    bits.push(`For: ${this._forLabel(r.members)}`);
    return bits.join(" · ");
  }

  // Who can get a reward. One dropdown of the family: no Everyone checkbox
  // and no Everyone / All row. A new reward, and a reward stored as everyone
  // (members null), starts with every person ticked. Ticking all of them is
  // saved as everyone, so a person added later is included. A shorter list
  // is only those people. Ticking nobody leaves the reward unavailable.
  _rewardWho(members) {
    const people = this._data.members || [];
    if (!people.length) {
      return `<small>Add family members under Family. Until then, anyone can get it.</small>`;
    }
    const selected = members == null ? new Set(people.map((m) => m.id)) : new Set(Array.isArray(members) ? members : []);
    const chosen = people.filter((m) => selected.has(m.id));
    const label = chosen.length ? chosen.map((m) => m.name).join(", ") : "Nobody";
    const options = people
      .map((m) => {
        const on = selected.has(m.id);
        return `<label class="eligible-option" role="option" aria-selected="${on}"><input type="checkbox" name="members" value="${esc(m.id)}" data-name="${esc(m.name)}" ${on ? "checked" : ""}> ${esc(m.name)}</label>`;
      })
      .join("");
    return `<div class="eligible" data-eligible>
      <button type="button" class="eligible-btn" data-eligible-toggle aria-haspopup="listbox" aria-expanded="false" aria-controls="who-can-get-it"><span data-eligible-label>${esc(label)}</span></button>
      <div class="eligible-menu" id="who-can-get-it" data-eligible-menu role="listbox" aria-multiselectable="true" aria-label="Who can get it" hidden>${options}</div>
      <small>All of the family starts selected. Leave them all selected and anyone can get it, including people you add later: Family saves that as everyone. Untick people to limit it to whoever is still selected. Untick all of them and nobody can get it.</small>
      <small class="eligible-warn" data-eligible-warn ${chosen.length ? "hidden" : ""}>Nobody is selected. Nobody can get this reward until you select someone.</small>
    </div>`;
  }

  // null: everyone (all ticked, or no family yet). A list: only those people.
  // []: nobody. The closed label lists names; it never offers an Everyone choice.
  _rewardMembers(values) {
    const people = this._data?.members || [];
    if (!people.length) return null;
    const picked = new Set(values.members || []);
    if (people.every((m) => picked.has(m.id))) return null;
    return people.filter((m) => picked.has(m.id)).map((m) => m.id);
  }

  _toggleEligible(button) {
    const menu = button.parentElement.querySelector("[data-eligible-menu]");
    const open = menu.hidden;
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  }

  _closeEligible() {
    const menu = this.shadowRoot?.querySelector("[data-eligible-menu]");
    if (!menu || menu.hidden) return;
    menu.hidden = true;
    menu.parentElement.querySelector("[data-eligible-toggle]")?.setAttribute("aria-expanded", "false");
  }

  // The closed label and the nobody warning follow the ticks, without
  // redrawing the form (a redraw would close the list).
  _syncEligible(root) {
    const boxes = [...root.querySelectorAll('input[name="members"]')];
    const names = boxes.filter((el) => el.checked).map((el) => el.dataset.name || "");
    const label = root.querySelector("[data-eligible-label]");
    if (label) label.textContent = names.length ? names.join(", ") : "Nobody";
    const warn = root.querySelector("[data-eligible-warn]");
    if (warn) warn.hidden = names.length > 0;
    for (const el of boxes) el.closest('[role="option"]')?.setAttribute("aria-selected", el.checked ? "true" : "false");
  }

  _feed(entries, review = false) {
    // An all-done day with no bonus points only marks the streak.
    entries = entries.filter((e) => !(e.kind === "bonus" && !e.points));
    if (!entries.length) return `<p class="empty">Nothing yet. Finished chores and spent points show up here.</p>`;
    return `<ul class="feed">${entries
      .map((e) => {
        const m = this._memberById(e.member);
        const gone = e.review === "rejected";
        const cls = gone ? "gone" : e.points >= 0 ? "plus" : "minus";
        const what = e.kind === "chore" ? `did <b>${esc(e.title)}</b>` : e.kind === "reward" ? `got <b>${esc(e.title)}</b>` : e.kind === "bonus" ? `earned a bonus: <b>${esc(e.title)}</b>` : e.kind === "penalty" ? `lost points: <b>${esc(e.title)}</b> didn't happen` : e.kind === "allowance" ? "got their <b>weekly allowance</b>" : `<b>${esc(e.title)}</b>`;
        const note = gone ? " · didn't happen" : e.review === "pending" ? " · to check" : e.auto ? " · checked automatically" : e.given === "to_give" ? " · to hand out" : e.given === "to_approve" ? " · waiting for a parent to say yes" : "";
        return `<li>${m ? this._avatar(m, true) : ""}<span class="what">${esc(m?.name || "Someone")} ${what}<br><small class="muted">${esc(whenText(e.at))}${note}</small></span>
          <span class="amount ${cls}">${signed(e.points)}</span>${review && e.kind === "chore" && !gone ? `<button class="btn bad" data-review="${esc(e.id)}" data-approved="0">Didn't happen</button>` : ""}</li>`;
      })
      .join("")}</ul>`;
  }

  _toast(text, bad = false, undo = null) {
    this._toastMsg = { text, bad, undo };
    this._renderOverlay();
    clearTimeout(this._toastTimer);
    // With Undo, long enough to notice the mistake and tap it.
    this._toastTimer = setTimeout(() => {
      this._toastMsg = null;
      this._renderOverlay();
    }, undo ? 10000 : 3500);
  }

  // ------------------------------------------------------------------ render

  _render() {
    if (!this._built) return;
    const title = this.shadowRoot.querySelector(".title");
    if (title) title.textContent = this._mode === "parents" ? "Parents" : "Family";
    const main = this.shadowRoot.querySelector("main");
    if (!this._data) {
      main.innerHTML = this._error ? `<p class="error" role="alert">${esc(this._error)}</p>` : `<p class="empty">Loading…</p>`;
      return;
    }
    const error = this._error ? `<p class="error" role="alert">${esc(this._error)}</p>` : "";
    main.innerHTML = error + (this._mode === "parents" ? this._renderParents() : this._renderFamily());
    if (this._mode === "parents") this._foldCards();
    this._fit();
    this._renderOverlay();
  }

  _renderOverlay() {
    const overlay = this.shadowRoot.querySelector(".overlay");
    if (!overlay) return;
    const t = this._toastMsg;
    const undo = t?.undo ? `<button class="undo" data-undo="${esc(t.undo)}">Undo</button>` : "";
    const toast = t ? `<div class="toast${t.bad ? " bad" : ""}" role="status"><span>${esc(t.text)}</span>${undo}</div>` : "";
    // Don't wipe a note someone is typing: only the toast changes then.
    if (this._sheet?.type === "note" && overlay.querySelector("[data-note-form]")) {
      overlay.querySelector(".toast")?.remove();
      if (toast) overlay.insertAdjacentHTML("beforeend", toast);
      return;
    }
    overlay.innerHTML = (this._sheet ? this._renderSheet() : "") + toast;
  }

  // Family ---------------------------------------------------------------------

  _renderFamily() {
    const d = this._data;
    if (!d.members.length) {
      return `<p class="empty">No family members yet. A parent adds them on the <b>Parents</b> dashboard.</p>`;
    }
    const member = this._memberById(this._member);
    // On someone's page: their own chores, then ones up for grabs for them.
    // On everyone's: only those up for grabs for everyone; ones up for grabs
    // for some people, and each person's own, are on their pages.
    const mine = member ? d.chores.filter((c) => !c.grab && c.can.includes(member.id)) : [];
    const grabs = d.chores.filter((c) => c.grab && (member ? c.can.includes(member.id) : !c.members?.length));
    const choreTiles = (chores, fit) =>
      `<div class="tiles" data-fit="${fit}">${chores
          .map((c) => {
            // On someone's own page, their name and picture on every tile
            // say nothing new; shared chores keep their list's name.
            const own = member && c.members?.length === 1 && c.members[0] === member.id;
            const who = !member && c.members?.length ? `<span class="who">${c.members.map((id) => this._memberById(id)).filter(Boolean).map((m) => this._avatar(m, true)).join("")}</span>` : "";
            // Only the round check box ticks it off, so a stray tap on the
            // tile does nothing.
            return `<div class="tile chore">
              ${c.emoji ? `<span class="emoji">${esc(c.emoji)}</span>` : ""}
              <span class="label">${esc(c.name)}</span>
              ${(c.list || c.on_list) && !own ? `<span class="sub">${esc(c.list || c.on_list)}</span>` : ""}${c.turn && !member ? `<span class="sub">${esc(this._memberById(c.turn)?.name || "Someone")}'s turn</span>` : c.turn ? `<span class="sub">Your turn</span>` : ""}${c.until_time ? `<span class="sub">Until ${esc(timeText(c.until_time))}</span>` : ""}${who}
              <span class="worth">+${pts(c.points)}</span>
              <button class="check" data-chore="${esc(c.id)}" aria-label="${esc(c.name)} is done"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></button></div>`;
          })
          .join("")}</div>`;
    const own = member?.own_today || {};
    const mineBody = mine.length
      ? choreTiles(mine, "chores")
      : `<p class="empty">${own.done ? `All done, ${esc(member.name)}! 🎉` : "Nothing of your own right now."}</p>`;
    const grabBody = grabs.length ? choreTiles(grabs, "grabs") : `<p class="empty">Nothing up for grabs right now.</p>`;
    const visibleRewards = this._visibleRewards(member);
    const rewardTiles = visibleRewards.length
      ? `<div class="tiles" data-fit="rewards">${visibleRewards
          .map((r) => {
            const short = member && member.points < r.points;
            const used = member && (r.used_by || []).includes(member.id);
            const goal = member && member.goal === r.id;
            const sub = this._rewardSub(r);
            const note = used ? AGAIN[r.limit] : short ? `${member.points} of ${r.points} · ${r.points - member.points} more to go` : LIMIT_TEXT[r.limit] || "";
            const bar = short && !used ? this._bar(member.points, r.points) : "";
            // Not enough yet: a tap offers to save up for it.
            return `<button class="tile${short ? " short" : ""}${goal ? " goal" : ""}" data-reward="${esc(r.id)}" ${used ? "disabled" : ""}>
              ${goal ? `<span class="sub goal-tag">🎯 Saving for this</span>` : ""}
              ${r.emoji ? `<span class="emoji">${esc(r.emoji)}</span>` : ""}
              <span class="label">${esc(r.name)}</span>${sub ? `<span class="sub">${esc(sub)}</span>` : ""}
              <span class="worth">${pts(r.points)}</span>
              ${bar}${note ? `<span class="sub">${esc(note)}</span>` : ""}</button>`;
          })
          .join("")}</div>`
      : `<p class="empty">${d.rewards.length ? (member ? `No rewards for ${esc(member.name)} right now.` : "No rewards for everyone right now.") : "No rewards yet. A parent adds them on the <b>Parents</b> dashboard."}</p>`;
    const feed = member ? d.recent.filter((e) => e.member === member.id) : d.recent;
    const controls = this._visibleControls();
    const home = controls.length ? this._section("home", "Home", `<div class="tiles home" data-fit="home">${this._controlTiles()}</div>`, controls.length) : "";
    const done = (d.done_today || []).filter((e) => !member || e.member === member.id);
    const doneTiles = `<div class="tiles" data-fit="done">${done
      .map((e) => {
        const m = this._memberById(e.member);
        return `<div class="tile done"><span class="tick" aria-hidden="true">✓</span>
          <span class="label">${esc(e.title)}</span>${!member && m ? `<span class="who">${this._avatar(m, true)}</span>` : ""}
          <span class="worth">+${pts(e.points)}</span></div>`;
      })
      .join("")}</div>`;
    // Someone's own routines on their page; every routine on everyone's.
    const routines = (d.routines || []).filter((r) => !member || r.who.includes(member.id));
    const goingFor = [this._familyGoalTile(), ...(member ? this._goingFor(member) : [])].filter(Boolean);
    const notes = (d.notes || []).filter((n) => !member || !n.member || n.member === member.id);
    // "Add a note" comes first, so it's never folded away with the rest.
    const noteTiles = `<div class="tiles notes" data-fit="notes"><button class="tile add-note" data-note-new><span class="emoji">📝</span><span class="label">Add a note</span></button>${notes.map((n) => this._noteTile(n)).join("")}</div>`;
    const events = (d.today || []).filter((e) => !member || !e.member || e.member === member.id);
    const eventTiles = `<div class="tiles events" data-fit="today">${
      events.length ? events.map((e) => this._eventTile(e, !member)).join("") : `<div class="tile event empty-day"><span class="label">Nothing today</span></div>`
    }</div>`;
    const meals = (d.meals || []).slice(0, 2).filter((day) => MEALS.some(([k]) => day[k]));
    const mealTiles = `<div class="tiles meals" data-fit="meals">${meals
      .map((day) => {
        const index = (d.meals || []).indexOf(day);
        return `<div class="tile meal"><span class="sub">${esc(dayText(day.date, index))}</span>
          ${MEALS.filter(([k]) => day[k]).map(([k, label]) => `<span class="meal-line"><small>${label}</small> ${esc(day[k])}</span>`).join("")}</div>`;
      })
      .join("")}</div>`;
    const cash = member && d.money ? ` <span class="streak-line">${esc(money(member.points, d.money))}</span>` : "";
    // Each section by key, shown in the order a parent set.
    // A parent can leave out sections with nothing in them. Notes stays: it
    // holds the Add a note button.
    const hide = !!d.hide_empty_sections;
    const sections = {
      going: goingFor.length ? this._section("going", "Going for", `<div class="tiles going" data-fit="going">${goingFor.join("")}</div>`) : "",
      chores: member && (mine.length || (own.total && !hide)) ? this._section("chores", "My chores", mineBody, mine.length) : "",
      grabs: grabs.length || (!member && !hide) ? this._section("grabs", "Up for grabs", grabBody, grabs.length) : "",
      routines: routines.length ? this._section("routines", "Routines", `<div class="tiles" data-fit="routines">${routines.map((r) => this._routineTile(r, member)).join("")}</div>`, routines.length) : "",
      notes: this._section("notes", "Notes", noteTiles, notes.length),
      today: events.length || (d.has_calendars && !hide) ? this._section("today", "Today", eventTiles, events.length, `<button class="btn sec-extra" data-days>Next few days</button>`) : "",
      meals: meals.length ? this._section("meals", "Meals", mealTiles) : "",
      done: done.length ? this._section("done", "Done today", doneTiles, done.length) : "",
      rewards: visibleRewards.length || !hide ? this._section("rewards", "Rewards", rewardTiles, visibleRewards.length) : "",
      home,
      lately: feed.length || !hide ? this._section("lately", "Lately", `<div data-fit="lately">${this._feed(feed.slice(0, 10))}</div>`) : "",
    };
    return `<h2>${member ? `Hi ${esc(member.name)}!${cash}` : "Who's here?"}</h2>
      ${this._people(this._pinnedMember() ? [this._pinnedMember()] : d.members, "data-member", this._member)}
      ${sectionOrder(d.section_order).map((key) => sections[key] || "").join("")}`;
  }

  // What someone's working toward: today's own chores, their streak, and
  // the reward they're saving for.
  // A routine: its steps ticked so far (for that person, or everyone's).
  _routineTile(r, member) {
    const total = r.steps.length;
    const done = (id) => (r.finished.includes(id) ? total : (r.ticked[id] || []).length);
    const finished = member ? r.finished.includes(member.id) : r.who.every((id) => r.finished.includes(id));
    const people = member
      ? `${this._bar(done(member.id), total)}<span class="sub">${finished ? "All done" : `${done(member.id)} of ${total} steps`}</span>`
      : `<span class="routine-people">${r.who
          .map((id) => this._memberById(id))
          .filter(Boolean)
          .map((m) => `<span class="pill${r.finished.includes(m.id) ? " won" : ""}">${esc(m.name)} ${r.finished.includes(m.id) ? "✓" : `${done(m.id)}/${total}`}</span>`)
          .join("")}</span>`;
    return `<button class="tile routine-tile${finished ? " won" : ""}" data-routine="${esc(r.id)}"><span class="emoji">${esc(r.emoji || "📋")}</span>
      <span class="label">${esc(r.name)}</span>${people}${r.points ? `<span class="worth">+${pts(r.points)}</span>` : ""}</button>`;
  }

  _routineSheet() {
    const s = this._sheet;
    const r = (this._data.routines || []).find((x) => x.id === s.id);
    if (!r) return "";
    const head = `<h3>${esc(r.emoji || "📋")} ${esc(r.name)}</h3>`;
    if (!s.member) {
      const people = r.who.map((id) => this._memberById(id)).filter(Boolean);
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(r.name)}">${head}
        <p class="muted">Who's doing it?</p>
        <div class="people small-people">${people.map((m) => `<button class="person" style="--c:${esc(m.color)}" data-routine-who="${esc(m.id)}" ${r.finished.includes(m.id) ? "disabled" : ""}>${this._avatar(m, true)}<span class="name">${esc(m.name)}${r.finished.includes(m.id) ? " ✓" : ""}</span></button>`).join("")}</div>
        <div class="actions"><button class="big" data-close>Close</button></div></div></div>`;
    }
    const member = this._memberById(s.member);
    const finished = r.finished.includes(s.member);
    const ticked = new Set(finished ? r.steps.map((_, i) => i) : r.ticked[s.member] || []);
    const steps = r.steps
      .map((text, i) => `<li><button class="step${ticked.has(i) ? " done" : ""}" data-routine-step="${i}" aria-pressed="${ticked.has(i)}" ${finished || this._busy ? "disabled" : ""}>
        <span class="box" aria-hidden="true">${ticked.has(i) ? "✓" : ""}</span><span>${esc(text)}</span></button></li>`)
      .join("");
    return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(r.name)}">${head}
      <p class="muted">${esc(member?.name || "")}${finished ? " finished it today." : `: tick each step. The last one finishes it${r.points ? ` for +${pts(r.points)}` : ""}.`}</p>
      ${this._bar(ticked.size, r.steps.length)}
      <ul class="steps">${steps}</ul>
      <div class="actions"><button class="big" data-close>Close</button></div></div></div>`;
  }

  async _routineStep(index) {
    const s = this._sheet;
    const r = (this._data.routines || []).find((x) => x.id === s?.id);
    if (!r || !s.member || this._busy) return;
    const member = this._memberById(s.member);
    const done = !(r.ticked[s.member] || []).includes(index);
    this._busy = true;
    // Show the tick straight away; the reply confirms it.
    r.ticked[s.member] = done ? [...(r.ticked[s.member] || []), index] : (r.ticked[s.member] || []).filter((i) => i !== index);
    this._renderOverlay();
    try {
      const res = await this._ws({ type: `${DOMAIN}/routine/step`, routine_id: r.id, member_id: s.member, step: index, done });
      if (res.entry) {
        this._sheet = null;
        this._toast(`${r.name} done, ${member?.name}!${r.points ? ` +${pts(r.points)}` : ""}`, false, res.entry.id);
        this._celebrate(member);
      }
      await this._load();
    } catch (err) {
      this._toast(err?.message || String(err), true);
      await this._load();
    } finally {
      this._busy = false;
      this._renderOverlay();
    }
  }

  // The goal the whole family works toward together.
  _familyGoalTile() {
    const g = this._data.family_goal;
    if (!g) return "";
    const left = Math.max(0, g.target - g.progress);
    return `<div class="tile going-tile${g.reached ? " won" : ""}"><span class="emoji">${esc(g.emoji || (g.reached ? "🎉" : "🏆"))}</span>
      <span class="label">${g.reached ? `We did it: ${esc(g.name)}!` : esc(g.name)}</span>
      ${this._bar(g.progress, g.target)}
      <span class="sub">${g.reached ? "Everyone's chores got us there." : `Together: ${g.progress} of ${g.target} points · ${left} to go`}</span></div>`;
  }

  _goingFor(member) {
    const b = this._data.bonus || {};
    const own = member.own_today || {};
    const tiles = [];
    if (own.total) {
      const doneCount = own.total - own.left;
      tiles.push(
        own.done
          ? `<div class="tile going-tile won"><span class="emoji">🎉</span><span class="label">All done today!</span>${b.all_done ? `<span class="worth">+${pts(b.all_done)}</span>` : ""}</div>`
          : `<div class="tile going-tile"><span class="emoji">✅</span><span class="label">Today's chores</span>${this._bar(doneCount, own.total)}
            <span class="sub">${doneCount} of ${own.total} done${own.missed ? ` · ${own.missed} missed` : b.all_done ? ` · finish them all for +${pts(b.all_done)}` : ""}</span></div>`,
      );
    }
    if (own.total || member.streak) {
      const n = member.streak || 0;
      const every = b.streak_days || 0;
      const next = every && b.streak ? (Math.floor(n / every) + 1) * every : 0;
      const missedAll = own.total && !own.done && own.missed >= own.left;
      const today = own.done ? "Today's done." : missedAll ? "Missed today, so it starts over tomorrow." : own.total ? `Finish today's chores to make it ${n + 1}.` : "No chores of your own today: it's safe.";
      tiles.push(`<div class="tile going-tile"><span class="emoji">🔥</span><span class="label">${n ? `${n} ${n === 1 ? "day" : "days"} in a row` : "Start a streak"}</span>
        ${next ? this._bar(n, next) : ""}<span class="sub">${today}${next ? ` ${next} days in a row: +${pts(b.streak)}` : ""}</span></div>`);
    }
    const goal = this._goal(member);
    if (goal) {
      tiles.push(`<button class="tile going-tile" data-reward="${esc(goal.id)}"><span class="emoji">${esc(goal.emoji || "🎯")}</span>
        <span class="label">Saving for ${esc(goal.name)}</span>${this._bar(member.points, goal.points)}
        <span class="sub">${member.points >= goal.points ? "You have enough! Tap to get it." : `${member.points} of ${goal.points} · ${goal.points - member.points} more to go`}</span></button>`);
    }
    return tiles;
  }

  _noteTile(n) {
    const m = this._memberById(n.member);
    // A parent's note can only be taken down by a parent.
    const canRemove = !n.parent || this._data.is_admin;
    return `<div class="tile note"${m ? ` style="--c:${esc(m.color)}"` : ""}>
      <span class="note-text">${esc(n.text)}</span>
      <span class="sub">${m ? `${this._avatar(m, true)} ${esc(m.name)}` : n.parent ? "From a parent" : ""}${n.until ? ` · until ${esc(dayText(n.until, -1))}` : ""}</span>
      ${canRemove ? `<button class="note-x" data-note-remove="${esc(n.id)}" aria-label="Take down this note">✕</button>` : ""}</div>`;
  }

  // Sections: the first row by default (as many as fit across the screen),
  // all of them, or closed. Remembered on this screen.
  _sectionMode(key) {
    // Going for is short and the point of someone's page: all of it.
    return this._sections[key] || (key === "going" ? "all" : "first");
  }

  _setSection(key, mode) {
    this._sections = { ...this._sections, [key]: mode };
    try {
      localStorage.setItem(SECTIONS_KEY, JSON.stringify(this._sections));
    } catch (_err) {
      // private browsing: just for now
    }
    this._render();
  }

  // `extra`: a button after the title, such as Today's "Next few days".
  _section(key, title, body, count, extra = "") {
    const closed = this._sectionMode(key) === "closed";
    const badge = count ? ` <span class="count">${count}</span>` : "";
    const head = `<h2 class="sec"><button class="sec-toggle" data-section-toggle="${key}" aria-expanded="${!closed}"><span class="chev"></span>${esc(title)}${badge}</button>${extra}</h2>`;
    return closed ? head : `${head}${body}<button class="more" data-more="${key}" hidden></button>`;
  }

  // An event; one that's already over today is faded and says so.
  _eventTile(e, showWho) {
    const m = this._memberById(e.member);
    const over = eventOver(e);
    return `<div class="tile event${over ? " over" : ""}"${m ? ` style="--c:${esc(m.color)}"` : ""}><span class="when">${esc(eventTime(e))}${over ? ` <span class="over-tag">Over</span>` : ""}</span>
      <span class="label">${esc(e.title)}</span>${m && showWho ? `<span class="who">${this._avatar(m, true)}</span>` : ""}</div>`;
  }

  // How many of today's events are over: the page is drawn again when it changes.
  _overCount() {
    return (this._data?.today || []).filter((e) => eventOver(e)).length;
  }

  // Hide what doesn't fit in the first row, and say how many there are.
  _fit() {
    const root = this.shadowRoot;
    if (!root || this._mode !== "family") return;
    for (const box of root.querySelectorAll("[data-fit]")) {
      const key = box.dataset.fit;
      const tiles = box.classList.contains("tiles");
      const items = tiles ? [...box.children] : [...box.querySelectorAll(".feed > li")];
      const first = tiles ? Math.max(1, getComputedStyle(box).gridTemplateColumns.split(" ").filter(Boolean).length) : 3;
      const all = this._sectionMode(key) === "all";
      items.forEach((el, i) => {
        el.hidden = !all && i >= first;
      });
      const more = root.querySelector(`[data-more="${key}"]`);
      if (more) {
        more.hidden = items.length <= first;
        more.textContent = all ? "Show fewer" : `Show all ${items.length}`;
      }
    }
  }

  // Home controls --------------------------------------------------------------

  _visibleControls() {
    const member = this._memberById(this._member);
    return (this._data?.controls || []).filter((c) => !member || !c.members?.length || c.members.includes(member.id));
  }

  _formatState(stateObj) {
    try {
      if (this._hass.formatEntityState) return this._hass.formatEntityState(stateObj);
    } catch (_err) {
      // fall back to the raw state below
    }
    const unit = stateObj.attributes?.unit_of_measurement;
    return unit ? `${stateObj.state} ${unit}` : stateObj.state;
  }

  // What a control shows and what a tap does, from its entity's live state.
  _controlView(control) {
    const stateObj = this._hass?.states?.[control.entity_id];
    const domain = control.entity_id.split(".")[0];
    const name = control.name || stateObj?.attributes?.friendly_name || control.label;
    const view = { name, icon: stateObj?.attributes?.icon || DOMAIN_ICONS[domain] || "mdi:eye", on: false, text: "", action: null, verb: "" };
    if (!stateObj || stateObj.state === "unavailable") return { ...view, text: "Not available", disabled: true };
    const state = stateObj.state;
    view.text = this._formatState(stateObj);
    switch (control.kind) {
      case "toggle":
        view.on = state === "on";
        return { ...view, action: "toggle", verb: view.on ? "Turn off" : "Turn on" };
      case "run": {
        const running = domain === "script" && state === "on";
        return { ...view, on: running, text: running ? "Running" : "", action: "run", verb: domain.endsWith("button") ? "Press" : "Start" };
      }
      case "open": {
        const open = state === "open" || state === "opening";
        return { ...view, on: open, action: open ? "close" : "open", verb: open ? "Close" : "Open" };
      }
      case "lock": {
        const locked = state === "locked";
        return { ...view, on: !locked, icon: locked ? "mdi:lock" : "mdi:lock-open-variant", action: locked ? "unlock" : "lock", verb: locked ? "Unlock" : "Lock" };
      }
      case "media": {
        const playing = state === "playing";
        const title = playing ? stateObj.attributes?.media_title : "";
        return { ...view, on: playing, text: title ? `${view.text} · ${title}` : view.text, action: "play_pause", verb: playing ? "Pause" : "Play" };
      }
      default:
        return view;
    }
  }

  _controlTiles() {
    const seen = {};
    const tiles = this._visibleControls()
      .map((c) => {
        seen[c.entity_id] = this._hass?.states?.[c.entity_id];
        const v = this._controlView(c);
        const icon = c.emoji ? `<span class="emoji">${esc(c.emoji)}</span>` : `<ha-icon class="icon" icon="${esc(v.icon)}"></ha-icon>`;
        const body = `${icon}<span class="label">${esc(v.name)}</span>${v.text ? `<span class="state">${esc(v.text)}</span>` : ""}`;
        if (!v.action) return `<div class="tile control view${v.disabled ? " off" : ""}">${body}</div>`;
        return `<button class="tile control${v.on ? " on" : ""}" data-control="${esc(c.id)}" ${v.disabled ? "disabled" : ""}>${body}
          <span class="do">${esc(v.verb)}</span></button>`;
      })
      .join("");
    this._seenStates = seen;
    return tiles;
  }

  _refreshControls() {
    const box = this.shadowRoot?.querySelector("main .tiles.home");
    if (box) {
      box.innerHTML = this._controlTiles();
      this._fit();
    } else this._seenStates = Object.fromEntries((this._data?.controls || []).map((c) => [c.entity_id, this._hass.states[c.entity_id]]));
  }

  async _useControl(id) {
    const control = this._data.controls.find((c) => c.id === id);
    if (!control) return;
    const v = this._controlView(control);
    if (!v.action || v.disabled) return;
    if (control.confirm) {
      this._sheet = { type: "control", id, action: v.action, verb: v.verb, name: v.name };
      this._renderOverlay();
      return;
    }
    await this._runControl(control, v.action, v.verb, v.name);
  }

  async _runControl(control, action, verb, name) {
    try {
      await this._ws({ type: `${DOMAIN}/control`, control_id: control.id, action });
      if (control.kind === "run") this._toast(`${verb === "Press" ? "Pressed" : "Started"} ${name}.`);
    } catch (err) {
      this._toast(err?.message || String(err), true);
    }
  }

  _renderSheet() {
    const s = this._sheet;
    const d = this._data;
    if (s.type === "note") {
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Add a note">
        <h3>Add a note</h3>
        <form data-note-form>
          <textarea name="text" rows="3" maxlength="200" placeholder="Dentist at 4, soccer bag by the door…" required></textarea>
          <p class="muted">From</p>
          <div class="people small-people">${d.members.map((m) => `<label class="person pick" style="--c:${esc(m.color)}"><input type="radio" name="member_id" value="${esc(m.id)}" ${m.id === s.member ? "checked" : ""}>${this._avatar(m, true)}<span class="name">${esc(m.name)}</span></label>`).join("")}
            <label class="person pick"><input type="radio" name="member_id" value="" ${s.member ? "" : "checked"}><span class="name">Everyone</span></label></div>
          <label class="field"><span>Show until (optional)</span><input type="date" name="until"></label>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button>
          <button class="big primary" type="submit" ${this._busy ? "disabled" : ""}>Put it up</button></div>
        </form></div></div>`;
    }
    if (s.type === "days") {
      const member = this._memberById(s.member);
      const days = (d.upcoming || []).map((day, index) => {
        const events = day.events.filter((e) => !member || !e.member || e.member === member.id);
        return `<li class="day"><h4>${esc(dayText(day.date, index))}</h4>${
          events.length ? `<div class="tiles events">${events.map((e) => this._eventTile(e, !member)).join("")}</div>` : `<p class="muted nothing">Nothing planned</p>`
        }</li>`;
      });
      return `<div class="sheet-bg" data-close><div class="sheet wide" role="dialog" aria-modal="true" aria-label="Next few days">
        <h3>Next few days</h3><ul class="days">${days.join("")}</ul>
        <div class="actions"><button class="big" data-close>Close</button></div></div></div>`;
    }
    if (s.type === "together") return this._togetherSheet();
    if (s.type === "routine") return this._routineSheet();
    if (s.type === "control") {
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(s.verb)}">
        <h3>${esc(s.verb)} ${esc(s.name)}?</h3>
        <div class="actions"><button class="big" data-close>No</button>
        <button class="big primary" data-confirm ${this._busy ? "disabled" : ""}>Yes</button></div></div></div>`;
    }
    // Ticked off with one tap: no sheet while it's saved.
    if (s.quick) return "";
    if (s.type === "chore") {
      const chore = d.chores.find((c) => c.id === s.id);
      if (!chore) return "";
      const member = this._memberById(s.member);
      if (!member) {
        const can = d.members.filter((m) => chore.can.includes(m.id));
        return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Who did it?">
          <h3>Who did ${esc(chore.name)}?</h3><p>+${pts(chore.points)}</p>
          ${this._people(can, "data-sheet-member", null)}
          <div class="actions"><button class="big" data-close>Cancel</button></div></div></div>`;
      }
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Chore done">
        <h3>${esc(chore.name)}</h3><p>Done, ${esc(member.name)}? That's +${pts(chore.points)}.</p>
        <div class="actions"><button class="big" data-close>Not yet</button>
        <button class="big primary" data-confirm ${this._busy ? "disabled" : ""}>Yes, it's done!</button></div></div></div>`;
    }
    const reward = d.rewards.find((r) => r.id === s.id);
    if (!reward) return "";
    const member = this._memberById(s.member);
    if (!member) {
      const can = this._eligibleMembers(reward).filter((m) => m.points >= reward.points && !(reward.used_by || []).includes(m.id));
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Who's it for?">
        <h3>Who's ${esc(reward.name)} for?</h3><p>${pts(reward.points)}</p>
        ${can.length ? this._people(can, "data-sheet-member", null) : `<p>Nobody has enough points on their own yet.</p>`}
        <div class="actions"><button class="big" data-close>Cancel</button>${this._canShare(reward) ? `<button class="big" data-together-start>Get it together</button>` : ""}</div></div></div>`;
    }
    if (member.points < reward.points) {
      const saving = member.goal === reward.id;
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Save up">
        <h3>${esc(reward.emoji || "")} ${esc(reward.name)}</h3>
        <p>${esc(member.name)} has ${member.points} of ${pts(reward.points)}: ${reward.points - member.points} more to go.${saving ? "" : " Save up for it?"}</p>
        ${this._bar(member.points, reward.points)}
        <div class="actions" style="margin-top:18px"><button class="big" data-close>Not now</button>
        ${saving ? `<button class="big" data-goal="">Stop saving for it</button>` : `<button class="big primary" data-goal="${esc(reward.id)}" ${this._busy ? "disabled" : ""}>Save for this</button>`}
        ${this._canShare(reward) ? `<button class="big" data-together-start>Get it together</button>` : ""}</div></div></div>`;
    }
    const tv = reward.kind === "tv_time" ? ` You'll get ${reward.minutes} minutes on ${esc(reward.tv_name || "the TV")} straight away.` : reward.kind === "music_time" ? ` You'll get ${reward.minutes} minutes of music on ${esc(reward.speaker_name || "the speaker")} straight away.` : " A parent will give it to you.";
    return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Get a reward">
      <h3>${esc(reward.name)}</h3><p>Spend ${pts(reward.points)} of ${esc(member.name)}'s ${member.points}?${tv}</p>
      <div class="actions"><button class="big" data-close>No</button>
      ${this._canShare(reward) ? `<button class="big" data-together-start>Get it together</button>` : ""}
      <button class="big primary" data-confirm ${this._busy ? "disabled" : ""}>Yes, please!</button></div></div></div>`;
  }

  // Others who could put points in with whoever's getting it. Only people
  // the reward is for: getting it together can't include anyone else.
  _shareable(reward) {
    return this._eligibleMembers(reward).filter((m) => !(reward.used_by || []).includes(m.id));
  }

  _canShare(reward) {
    return this._shareable(reward).length >= 2;
  }

  // Getting a reward together: pick who's putting in points; a parent says yes.
  _togetherSheet() {
    const s = this._sheet;
    const d = this._data;
    const reward = d.rewards.find((r) => r.id === s.id);
    if (!reward) return "";
    const picked = s.with.filter((id) => this._memberById(id));
    const people = this._shareable(reward);
    const shares = picked.length >= 2 ? splitPoints(reward.points, picked.map((id) => [id, this._memberById(id).points])) : null;
    const broke = shares && reward.points ? picked.filter((id) => !shares[id]).map((id) => this._memberById(id).name) : [];
    const have = picked.reduce((sum, id) => sum + Math.max(0, this._memberById(id).points), 0);
    let line;
    if (picked.length < 2) line = "Who's putting in points? Pick two or more.";
    else if (!shares) line = `Together you have ${have} of ${pts(reward.points)}: ${reward.points - have} more to go.`;
    else if (broke.length) line = `${esc(namesText(broke))} ${broke.length === 1 ? "has" : "have"} no points to put in.`;
    else line = picked.map((id) => `${esc(this._memberById(id).name)} ${shares[id]}`).join(" · ");
    const ready = shares && !broke.length;
    return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Get it together">
      <h3>${esc(reward.emoji || "")} ${esc(reward.name)}</h3><p>Get it together: ${pts(reward.points)}, shared. A parent says yes first, and until then the points are held.</p>
      ${this._people(people, "data-together", picked)}
      <p class="split${ready ? " ready" : ""}">${line}</p>
      <div class="actions"><button class="big" data-close>Cancel</button>
      <button class="big primary" data-confirm ${ready && !this._busy ? "" : "disabled"}>Ask a parent</button></div></div></div>`;
  }

  // Parents ---------------------------------------------------------------------

  _renderParents() {
    const d = this._data;
    const checks = (d.to_check?.length || 0) + (d.to_give?.length || 0) + (d.to_approve?.length || 0);
    const tabs = [
      ["review", `To check${checks ? `<span class="badge">${checks}</span>` : ""}`],
      ["chores", "Chores"],
      ["routines", "Routines"],
      ["rewards", "Rewards"],
      ["home", "Home"],
      ["meals", "Meals"],
      ["notes", "Notes"],
      ["family", "Family"],
      ["history", "History"],
    ];
    const bar = `<div class="tabs" role="tablist">${tabs
      .map(([id, label]) => `<button class="tab" role="tab" data-tab="${id}" aria-selected="${this._tab === id}">${label}</button>`)
      .join("")}</div>`;
    const body = {
      review: () => this._renderReview(),
      chores: () => this._renderChores(),
      routines: () => this._renderRoutines(),
      rewards: () => this._renderRewards(),
      home: () => this._renderHome(),
      meals: () => this._renderMeals(),
      notes: () => this._renderNotes(),
      family: () => this._renderMembers(),
      history: () => `<div class="card">${this._feed(d.history || [], true)}</div>`,
    }[this._tab]();
    return bar + body;
  }

  // One-tap points for how someone's doing ("Kind to a sibling" +2,
  // "Not listening" -1). The buttons are the parents' own; each tap is a
  // points change in History, like Change points.
  _quickCard() {
    const d = this._data;
    const buttons = d.settings?.quick_points || [];
    if (this._edit?.collection === "quick_points") return `<div class="card"><h2>Quick points</h2>${this._quickForm(buttons)}</div>`;
    const rows = buttons.length && d.members.length
      ? `<ul class="rows quick">${d.members
          .map((m) => `<li>${this._avatar(m, true)}<span class="grow"><b>${esc(m.name)}</b><small>${pts(m.points)}</small></span>
            <span class="quick-buttons">${buttons
              .map((b, i) => `<button class="btn ${b.points > 0 ? "good" : "bad"}" data-quick="${i}" data-member-id="${esc(m.id)}" ${this._busy ? "disabled" : ""}>${b.emoji ? `${esc(b.emoji)} ` : ""}${esc(b.label)} ${b.points > 0 ? "+" : "−"}${Math.abs(b.points)}</button>`)
              .join("")}</span></li>`)
          .join("")}</ul>`
      : `<p class="empty">${d.members.length ? "No buttons yet. Add a few for the things you want to notice, good and not so good." : "Add your family first."}</p>`;
    return `<div class="card"><h2>Quick points</h2>
      <p class="muted">One tap gives or takes points straight away. It shows in History.</p>
      ${rows}<button class="btn" data-new="quick_points">${buttons.length ? "Change the buttons" : "Add buttons"}</button></div>`;
  }

  _quickForm(buttons) {
    const rows = [...buttons, { label: "", emoji: "", points: "" }, { label: "", emoji: "", points: "" }];
    return `<form class="edit" data-quick-form>
      <p class="muted">Use a minus for points taken away, like −1. Leave a row empty to remove it. Up to 12 buttons.</p>
      <ul class="rows">${rows
        .map((b) => `<li><input class="item-emoji" name="emoji" maxlength="8" value="${esc(b.emoji || "")}" placeholder="+" aria-label="Emoji">
          <input class="grow" name="label" maxlength="40" value="${esc(b.label || "")}" placeholder="Kind to a sibling" aria-label="What it's for">
          <input type="number" name="points" min="-10000" max="10000" value="${esc(b.points)}" placeholder="2" aria-label="Points" style="width:90px"></li>`)
        .join("")}</ul>
      <div class="form-actions"><button class="btn primary" type="submit">Save</button><button class="btn" type="button" data-cancel>Cancel</button></div></form>`;
  }

  _renderReview() {
    const d = this._data;
    const check = d.to_check.length
      ? `<ul class="rows">${d.to_check
          .map((e) => {
            const m = this._memberById(e.member);
            return `<li>${m ? this._avatar(m, true) : ""}<span class="grow">${esc(m?.name || "Someone")}: <b>${esc(e.title)}</b><small>${esc(whenText(e.at))} · +${pts(e.points)} given</small></span>
              <button class="btn good" data-review="${esc(e.id)}" data-approved="1">Done right</button>
              <span class="penalty"><input type="number" min="0" max="10000" data-penalty-for="${esc(e.id)}" placeholder="${esc(e.penalty ?? d.settings?.penalty ?? 0)}" aria-label="Extra points to take if it didn't happen">
              <button class="btn bad" data-review="${esc(e.id)}" data-approved="0">Didn't happen</button></span></li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">Nothing to check. Chores the kids mark done show up here.</p>`;
    const approve = (d.to_approve || []).length
      ? `<div class="card"><h2>Rewards to say yes to</h2>
        <p class="muted">Bought together: each one's points are held until you say yes. <b>No</b> gives them back.</p>
        <ul class="rows">${d.to_approve
          .map((r) => {
            const people = r.shares.map((sh) => this._memberById(sh.member)).filter(Boolean);
            const split = r.shares.map((sh) => `${esc(this._memberById(sh.member)?.name || "Someone")} ${sh.points}`).join(" · ");
            return `<li><span class="avatars">${people.map((m) => this._avatar(m, true)).join("")}</span><span class="grow">${esc(namesText(people.map((m) => m.name)))}: <b>${esc(r.title)}</b><small>${esc(whenText(r.at))} · ${split}</small></span>
              <button class="btn good" data-approve="${esc(r.group)}" data-yes="1">Yes</button>
              <button class="btn bad" data-approve="${esc(r.group)}" data-yes="0">No</button></li>`;
          })
          .join("")}</ul></div>`
      : "";
    const give = d.to_give.length
      ? `<ul class="rows">${d.to_give
          .map((e) => {
            const people = (e.together || [e.member]).map((id) => this._memberById(id)).filter(Boolean);
            const who = people.length ? namesText(people.map((m) => m.name)) : "Someone";
            return `<li><span class="avatars">${people.map((m) => this._avatar(m, true)).join("")}</span><span class="grow">${esc(who)}: <b>${esc(e.title)}</b><small>${esc(whenText(e.at))}</small></span>
              <button class="btn primary" data-given="${esc(e.id)}">Handed out</button></li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No rewards to hand out.</p>`;
    const auto = d.settings?.auto_check || "";
    return `${this._quickCard()}${approve}<div class="card"><h2>Chores to check</h2>
        <p class="muted">Points are given as soon as a chore is marked done. <b>Didn't happen</b> takes them back${d.todo_lists.length ? " and puts a to-do item back on its list" : ""}, and takes the penalty in the box next to it: the chore's own penalty, or the family's. Type a number to change it this time.</p>${check}
        <form class="inline penalty-setting" data-penalty-setting>
          <label class="field"><span>When a chore didn't happen, also take away</span>
            <span><input type="number" name="penalty" min="0" max="10000" value="${esc(d.settings?.penalty ?? 0)}" style="width:100px"> points <small>(0: just take back its points)</small></span></label>
          <button class="btn" type="submit">Save</button></form>
        <label class="field" style="margin-top:16px"><span>Count chores nobody checked as done right</span>
          <select data-auto-check>${AUTO_CHECKS.map((a) => `<option value="${a.id}" ${auto === a.id ? "selected" : ""}>${a.label}</option>`).join("")}</select>
          <small>You can still mark one <b>Didn't happen</b> from History.</small></label></div>
      <div class="card"><h2>Rewards to hand out</h2>${give}</div>
      ${this._phonesCard()}`;
  }

  _phonesCard() {
    const st = this._data.settings || {};
    const phones = this._choices?.notify || [];
    const picked = new Set(st.notify_targets || []);
    const list = phones.length
      ? `<div class="inline">${phones.map((p) => `<label class="check"><input type="checkbox" name="notify_targets" value="${esc(p.service)}" ${picked.has(p.service) ? "checked" : ""}> ${esc(p.name)}</label>`).join("")}</div>`
      : `<small>No phones yet. Install the Home Assistant app on a phone and log in, and it shows up here.</small>`;
    return `<div class="card"><h2>Phones</h2>
      <p class="muted">Get a notification on your phone, and check chores from it with <b>Done right</b> and <b>Didn't happen</b>. Only a parent's phone can check them.</p>
      <form class="edit" data-phones>
        <div class="field"><span>Send to</span>${list}</div>
        <label class="check"><input type="checkbox" name="notify_done" ${st.notify_done ? "checked" : ""}> When a chore is marked done</label>
        <label class="check"><input type="checkbox" name="notify_rewards" ${st.notify_rewards ? "checked" : ""}> When a reward needs handing out</label>
        <label class="check"><input type="checkbox" name="weekly_summary" ${st.weekly_summary ? "checked" : ""}> A summary of the week, on Sunday at 6:00 PM</label>
        <div class="form-actions"><button class="btn primary" type="submit">Save</button></div>
      </form></div>`;
  }

  _whoText(ids) {
    if (!ids?.length) return "Anyone";
    return ids.map((id) => this._memberById(id)?.name).filter(Boolean).join(", ");
  }

  _whoChecks(selected) {
    const d = this._data;
    if (!d.members.length) return `<small>Add family members first, under Family.</small>`;
    return `<div class="inline">${d.members
      .map((m) => `<label class="check"><input type="checkbox" name="members" value="${esc(m.id)}" ${selected?.includes(m.id) ? "checked" : ""}> ${esc(m.name)}</label>`)
      .join("")}</div><small>None ticked: anyone can do it.</small>`;
  }

  // Routines: step-by-step checklists such as Morning or Bedtime.
  _renderRoutines() {
    const d = this._data;
    const all = d.all_routines || [];
    const edit = this._edit;
    const last = all.length - 1;
    const rows = all.length
      ? `<ul class="rows">${all
          .map((r, i) => {
            const who = (r.members || []).map((id) => this._memberById(id)?.name).filter(Boolean);
            const when = [r.days?.length && r.days.length < 7 ? r.days.map((x) => DAYS[x]).join(", ") : "Every day", r.from_time || r.until_time ? `${r.from_time ? timeText(r.from_time) : "…"} to ${r.until_time ? timeText(r.until_time) : "…"}` : ""].filter(Boolean).join(" · ");
            return `<li><span class="grow">${r.emoji ? `${esc(r.emoji)} ` : ""}<b>${esc(r.name)}</b>${r.enabled === false ? " <small>(hidden)</small>" : ""}
              <small>${r.steps.length} ${r.steps.length === 1 ? "step" : "steps"} · +${pts(r.points)} when finished · ${esc(who.length ? namesText(who) : "Everyone")} · ${esc(when)}</small></span>
              <button class="btn" data-move="routines" data-id="${esc(r.id)}" data-offset="-1" ${i === 0 ? "disabled" : ""} aria-label="Move up">↑</button>
              <button class="btn" data-move="routines" data-id="${esc(r.id)}" data-offset="1" ${i === last ? "disabled" : ""} aria-label="Move down">↓</button>
              <button class="btn" data-edit="routines" data-id="${esc(r.id)}">Edit</button>
              <button class="btn bad" data-delete="routines" data-id="${esc(r.id)}">Remove</button></li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No routines yet. A morning or bedtime checklist is a good start.</p>`;
    const form = edit?.collection === "routines" ? this._routineForm(edit.item) : `<button class="btn primary" data-new="routines">Add a routine</button>`;
    return `<div class="card"><h2>Routines</h2>
      <p class="muted">A checklist someone works through on the Family dashboard, one step at a time. Ticking the last step finishes it: the points are given straight away and it waits under <b>To check</b>, like a chore. Ticked steps start fresh each day.</p>
      ${rows}${form}</div>`;
  }

  _routineForm(item) {
    const r = item || { name: "", points: 5, members: [], steps: [], enabled: true };
    return `<form class="edit" data-form="routines" data-id="${esc(r.id || "")}">
      <div class="inline">
        <label class="field"><span>Routine</span><input type="text" name="name" value="${esc(r.name)}" required placeholder="Morning"></label>
        <label class="field"><span>Emoji</span><input type="text" name="emoji" value="${esc(r.emoji || "")}" size="3" placeholder="🌅"></label>
        <label class="field"><span>Points when finished</span><input type="number" name="points" min="0" max="10000" value="${esc(r.points)}"></label>
      </div>
      <label class="field"><span>Steps, one on each line</span><textarea name="steps" rows="6" required placeholder="🛏️ Make your bed&#10;👕 Get dressed&#10;🪥 Brush your teeth&#10;🎒 Pack your bag">${esc((r.steps || []).join("\n"))}</textarea>
        <small>Up to 20. Start a line with an emoji if you like.</small></label>
      <div class="field"><span>Who does it</span>${this._whoChecks(r.members)}</div>
      <div class="field"><span>Which days</span><div class="inline">${DAYS.map((x, i) => `<label class="check"><input type="checkbox" name="days" value="${i}" ${(r.days || []).includes(i) ? "checked" : ""}> ${x}</label>`).join("")}</div>
        <small>None ticked: every day. School mornings? Tick Monday to Friday.</small></div>
      <div class="inline">
        <label class="field"><span>Shown from</span><input type="time" name="from_time" value="${esc(r.from_time || "")}"></label>
        <label class="field"><span>Until</span><input type="time" name="until_time" value="${esc(r.until_time || "")}"></label>
        <small style="align-self:end">Empty: all day.</small>
      </div>
      <label class="check"><input type="checkbox" name="enabled" ${r.enabled !== false ? "checked" : ""}> Show it on the Family dashboard</label>
      <div class="form-actions"><button class="btn primary" type="submit">Save routine</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  _renderChores() {
    const d = this._data;
    const edit = this._edit;
    const chores = d.all_chores.length
      ? `<ul class="rows">${d.all_chores
          .map((c) => `<li><span class="grow">${c.emoji ? `${esc(c.emoji)} ` : ""}<b>${esc(c.name)}</b>${c.enabled ? "" : " (off)"}
              <small>+${pts(c.points)} · ${esc(repeatText(c))}${whenShown(c) ? ` · ${esc(whenShown(c))}` : ""} · ${esc(c.turns ? `Turns: ${this._whoText(c.members)}` : c.grab || !c.members?.length ? `Up for grabs: ${this._whoText(c.members)}` : `Their own: ${this._whoText(c.members)}`)}${c.todo_list ? ` · on ${esc(this._listName(c.todo_list))}` : ""}</small></span>
              <button class="btn" data-edit="chores" data-id="${esc(c.id)}">Edit</button>
              <button class="btn bad" data-delete="chores" data-id="${esc(c.id)}">Delete</button></li>`)
          .join("")}</ul>`
      : `<p class="empty">No chores added here yet.</p>`;
    const choreForm = edit?.collection === "chores" ? this._choreForm(edit.item) : `<button class="btn primary" data-new="chores">Add a chore</button>`;
    const lists = d.todo_lists.length
      ? `<ul class="rows">${d.todo_lists
          .map((t) => {
            const own = (t.items || []).filter((i) => i.rated).length;
            return `<li><span class="grow"><b>${esc(t.name)}</b><small>+${pts(t.points)} each unless the item says otherwise${own ? ` · ${own} with their own points` : ""} · ${esc(t.grab || !t.members?.length ? `Up for grabs: ${this._whoText(t.members)}` : `Their own: ${this._whoText(t.members)}`)}${t.due_only ? " · only when due" : ""}</small></span>
              <button class="btn" data-edit="todo_lists" data-id="${esc(t.id)}">Points for items</button>
              <button class="btn" data-edit="todo_lists" data-id="${esc(t.id)}">Edit</button>
              <button class="btn bad" data-delete="todo_lists" data-id="${esc(t.id)}">Remove</button></li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No to-do lists yet.</p>`;
    const listForm = edit?.collection === "todo_lists" ? this._listForm(edit.item) : `<button class="btn primary" data-new="todo_lists">Add a to-do list</button>`;
    return `${this._choreMatrix()}<div class="card"><h2>Chores</h2>${chores}${choreForm}</div>
      <div class="card"><h2>Chores from to-do lists</h2>
        <p class="muted">Every open item on these lists is a chore. Put the points at the end of an item to change them, like <b>Feed the dog [5]</b>. When it's marked done, the item is ticked off its list.</p>
        ${lists}${listForm}</div>`;
  }

  // Who does what, lined up: a row per chore, a column per person, grouped
  // by their own chores, turns, and up for grabs.
  _choreMatrix() {
    const d = this._data;
    const people = d.members;
    if (!people.length) return "";
    const lists = d.todo_lists.map((t) => ({ ...t, name: t.name || this._listName(t.entity_id), list: true }));
    const all = [...d.all_chores.filter((c) => c.enabled), ...lists];
    const kind = (c) => (c.turns ? "turns" : !c.members?.length ? "everyone" : c.grab ? "grab" : "own");
    const groups = [
      ["own", "Their own", "Each person ticked does it. Counts for the all-done bonus and streaks."],
      ["turns", "Taking turns", "Their own chore, for whoever's turn it is."],
      ["grab", "Up for grabs, for some", "Whoever's first, of the people ticked. Extra points."],
      ["everyone", "Up for grabs, for everyone", "Whoever's first. Extra points."],
    ];
    const mark = {
      own: (c, m) => (c.members.includes(m.id) ? `<span class="mark own" title="${esc(m.name)}'s own">●</span>` : ""),
      turns: (c, m) => (c.members.includes(m.id) ? (this._currentTurn(c) === m.id ? `<span class="mark own" title="${esc(m.name)}'s turn now">↻ now</span>` : `<span class="mark turn" title="Takes turns">↻</span>`) : ""),
      grab: (c, m) => (c.members.includes(m.id) ? `<span class="mark grab" title="Up for grabs for ${esc(m.name)}">○</span>` : ""),
      everyone: () => `<span class="mark grab" title="Up for grabs">○</span>`,
    };
    const head = `<tr><th class="chore"></th>${people.map((m) => `<th>${this._avatar(m, true)}<span>${esc(m.name)}</span></th>`).join("")}</tr>`;
    const body = groups
      .map(([key, title, help]) => {
        const rows = all.filter((c) => kind(c) === key);
        if (!rows.length) return "";
        return `<tr class="group"><th colspan="${people.length + 1}">${title} <small>${help}</small></th></tr>${rows
          .map((c) => {
            const when = c.list ? `To-do list · +${pts(c.points)} each` : `+${pts(c.points)} · ${repeatText(c)}${whenShown(c) ? ` · ${whenShown(c)}` : ""}`;
            return `<tr><th class="chore">${c.emoji ? `${esc(c.emoji)} ` : ""}${esc(c.name)}<small>${esc(when)}</small></th>${people.map((m) => `<td>${mark[key](c, m)}</td>`).join("")}</tr>`;
          })
          .join("")}`;
      })
      .join("");
    // How many of their own chores today, and how many are left.
    const totals = `<tr class="totals"><th>Their own today</th>${people
      .map((m) => {
        const own = m.own_today || {};
        return `<td>${own.total ? `${own.total - own.left} of ${own.total}` : "–"}</td>`;
      })
      .join("")}</tr>`;
    return `<div class="card matrix"><h2>Who does what</h2>
      <p class="muted">● their own &nbsp; ↻ taking turns &nbsp; ○ up for grabs. Only chores shown on the Family dashboard.</p>
      ${body ? `<div class="matrix-wrap"><table>${head}${body}${totals}</table></div>` : `<p class="empty">No chores yet.</p>`}</div>`;
  }

  _choreForm(item) {
    const c = item || { name: "", points: 5, repeat: "daily", members: [], enabled: true };
    return `<form class="edit" data-form="chores" data-id="${esc(c.id || "")}">
      <div class="inline">
        <label class="field"><span>Chore</span><input type="text" name="name" value="${esc(c.name)}" required placeholder="Make your bed"></label>
        <label class="field"><span>Emoji</span><input type="text" name="emoji" value="${esc(c.emoji || "")}" size="3" placeholder="🛏️"></label>
        <label class="field"><span>Points</span><input type="number" name="points" min="0" max="10000" value="${esc(c.points)}"></label>
        <label class="field"><span>Penalty if it didn't happen</span><input type="number" name="penalty" min="0" max="10000" value="${esc(c.penalty ?? "")}" placeholder="Family's (${esc(this._data.settings?.penalty ?? 0)})"></label>
        <label class="field"><span>Comes back</span><select name="repeat" data-repeat>${REPEATS.map((r) => `<option value="${r.id}" ${r.id === c.repeat ? "selected" : ""}>${r.label}</option>`).join("")}</select></label>
        <label class="field" data-days-field ${c.repeat === "after_days" ? "" : "hidden"}><span>Days after it's done</span><input type="number" name="repeat_days" min="1" max="365" value="${esc(c.repeat_days || 3)}"></label>
      </div>
      <label class="field"><span>Also keep it on a to-do list</span><select name="todo_list">
        <option value="">No list</option>${(this._choices?.todo_lists || []).map((l) => `<option value="${esc(l.entity_id)}" ${l.entity_id === c.todo_list ? "selected" : ""}>${esc(l.name)}</option>`).join("")}</select>
        <small>It's added to the list while it can be done, ticked off when it's done, and opened again when it comes back. If the list already has an item with the same name, that item is used instead of adding another.</small></label>
      <label class="field"><span>When it shows</span><select name="due_only">
        <option value="" ${c.due_only ? "" : "selected"}>Always, on its days and hours</option>
        <option value="1" ${c.due_only ? "selected" : ""}>Only when its to-do item is due today or overdue</option></select>
        <small>Needs a to-do list above. The due date set on the list decides; an item with no due date always shows.</small></label>
      <div class="field"><span>Which days</span><div class="inline">${DAYS.map((d, i) => `<label class="check"><input type="checkbox" name="days" value="${i}" ${(c.days || []).includes(i) ? "checked" : ""}> ${d}</label>`).join("")}</div>
        <small>None ticked: every day. Trash day? Tick just that day.</small></div>
      <div class="inline">
        <label class="field"><span>Shown from</span><input type="time" name="from_time" value="${esc(c.from_time || "")}"></label>
        <label class="field"><span>Until</span><input type="time" name="until_time" value="${esc(c.until_time || "")}"></label>
        <small style="align-self:end">Empty: all day. For a morning or bedtime chore, such as 6:00 AM to 9:00 AM.</small>
      </div>
      ${this._remindField(c)}
      <div class="field"><span>Who can do it</span>${this._whoChecks(c.members)}</div>
      ${this._grabField(c.grab)}
      <label class="check"><input type="checkbox" name="turns" data-turns ${c.turns ? "checked" : ""}> They take turns (tick two or more people above)</label>
      <div class="inline" data-turn-fields ${c.turns ? "" : "hidden"}>
        <label class="field"><span>The turn moves on</span><select name="turn_every">${TURN_EVERY.map((t) => `<option value="${t.id}" ${(c.turn_every || "time") === t.id ? "selected" : ""}>${t.label}</option>`).join("")}</select></label>
        <label class="field"><span>Whose turn is it now?</span><select name="turn_first">${this._data.members.map((m) => `<option value="${esc(m.id)}" ${this._currentTurn(c) === m.id ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select></label>
      </div>
      <label class="check"><input type="checkbox" name="enabled" ${c.enabled ? "checked" : ""}> Show it on the Family dashboard</label>
      <div class="form-actions"><button class="btn primary" type="submit">Save chore</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  // Their own chore, or up for grabs among the people ticked.
  _grabField(grab) {
    return `<label class="field"><span>How it's done</span><select name="grab">
      <option value="" ${grab ? "" : "selected"}>Their own chore: each one ticked does it</option>
      <option value="1" ${grab ? "selected" : ""}>Up for grabs: whoever's first, for extra points</option></select>
      <small>Their own chores count for the all-done bonus and streaks; up for grabs is extra. Nobody ticked: up for grabs for everyone. Taking turns is always their own chore.</small></label>`;
  }

  // Whose turn a chore is now, from the Family dashboard's view of it.
  _currentTurn(c) {
    return this._data.chores.find((x) => x.id === c.id)?.turn || c.turn_first || c.members?.[0];
  }

  _listName(entityId) {
    return (this._choices?.todo_lists || []).find((l) => l.entity_id === entityId)?.name || entityId;
  }

  _listForm(item) {
    const t = item || { entity_id: "", points: 5, members: [] };
    const used = new Set(this._data.todo_lists.map((x) => x.entity_id));
    const options = (this._choices?.todo_lists || []).filter((l) => l.entity_id === t.entity_id || !used.has(l.entity_id));
    return `<form class="edit" data-form="todo_lists">
      <div class="inline">
        <label class="field"><span>To-do list</span><select name="entity_id" ${item ? "disabled" : ""}>${options.map((l) => `<option value="${esc(l.entity_id)}" ${l.entity_id === t.entity_id ? "selected" : ""}>${esc(l.name)}</option>`).join("") || `<option value="">No to-do lists in Home Assistant</option>`}</select></label>
        <label class="field"><span>Points for each item</span><input type="number" name="points" min="0" max="10000" value="${esc(t.points)}"></label>
        <label class="field"><span>Penalty if one didn't happen</span><input type="number" name="penalty" min="0" max="10000" value="${esc(t.penalty ?? "")}" placeholder="Family's (${esc(this._data.settings?.penalty ?? 0)})"></label>
      </div>
      <div class="field"><span>Who can do them</span>${this._whoChecks(t.members)}</div>
      ${this._grabField(t.grab)}
      <label class="field"><span>When items show</span><select name="due_only">
        <option value="" ${t.due_only ? "" : "selected"}>Always, while they're on the list</option>
        <option value="1" ${t.due_only ? "selected" : ""}>Only when due today or overdue</option></select>
        <small>With a due time, an item shows once that time comes. Items with no due date always show.</small></label>
      ${item ? this._itemPoints(t) : ""}
      <div class="form-actions"><button class="btn primary" type="submit">Save list</button><button class="btn" type="button" data-cancel>Cancel</button></div>
      ${item ? `<input type="hidden" name="entity_id_keep" value="${esc(t.entity_id)}">` : ""}
    </form>`;
  }

  // Say a chore on speakers at a time while someone still has it to do.
  _remindField(c) {
    const players = this._choices?.players || [];
    const voice = this._data.settings?.reminder_tts;
    const picked = new Set(c.remind_speakers || []);
    const boxes = players.length
      ? `<div class="inline">${players.map((p) => `<label class="check"><input type="checkbox" name="remind_speakers" value="${esc(p.entity_id)}" ${picked.has(p.entity_id) ? "checked" : ""}> ${esc(p.name)}</label>`).join("")}</div>`
      : `<small>No speakers in Home Assistant yet.</small>`;
    return `<div class="field"><span>Say it on a speaker</span>
      <label class="field"><span>At</span><input type="time" name="remind_time" value="${esc(c.remind_time || "")}" style="max-width:160px"></label>
      ${boxes}
      <small>${voice ? "At this time, on its days, the speakers say who still has it to do. Nothing is said once it's done." : "Pick a voice first under <b>Family</b> → <b>Speaker reminders</b>."}</small></div>`;
  }

  _itemPoints(list) {
    const items = list.items || [];
    const row = (i) => `<li class="${i.skip ? "skipped" : ""}"><input class="item-emoji" maxlength="8" aria-label="Emoji for ${esc(i.name)}" data-item-emoji="${esc(i.name)}" value="${esc(i.emoji || "")}" placeholder="+"><span class="item-name">${esc(i.name)}</span>
            <span class="item-who">${this._data.members
              .map((m) => `<label class="chip"><input type="checkbox" data-item-member="${esc(i.name)}" value="${esc(m.id)}" ${(i.members || []).includes(m.id) ? "checked" : ""}>${esc(m.name)}</label>`)
              .join("")}<label class="chip leave-out"><input type="checkbox" data-item-skip="${esc(i.name)}" ${i.skip ? "checked" : ""}>Leave out</label></span>
            <input type="number" min="0" max="10000" aria-label="Points for ${esc(i.name)}" data-item-name="${esc(i.name)}" data-rated="${i.rated ? 1 : ""}" data-unrated="${esc(i.unrated)}" value="${i.rated ? esc(i.points) : ""}" placeholder="${esc(i.unrated)}"></li>`;
    // Items left out go in their own folded group at the end, so the rows
    // in use stay short.
    const used = items.filter((i) => !i.skip);
    const left = items.filter((i) => i.skip);
    const rows = items.length
      ? `${used.length ? `<ul class="items">${used.map(row).join("")}</ul>` : ""}${left.length ? `<details class="left-out"><summary>Left out (${left.length})</summary><ul class="items">${left.map(row).join("")}</ul></details>` : ""}`
      : `<p class="muted">Nothing open on this list right now.</p>`;
    return `<div class="field"><span>Single items: emoji, who and points</span>
      <small>Give an item an emoji for the Family dashboard. Tick <b>Leave out</b> for an item that isn't a chore: it stays on the list but never shows on the Family dashboard. Tick who an item is for; nobody ticked: the people ticked for the whole list. Give it its own points; empty: the list's points, or the points written in the item. Repeating items keep both when they come back.</small>${rows}</div>`;
  }

  _familyGoalCard() {
    const g = this._data.family_goal;
    const editing = this._edit?.collection === "family_goal";
    const status = g
      ? `<div class="rows goal-status"><span class="grow">${esc(g.emoji || "🏆")} <b>${esc(g.name)}</b>${this._bar(g.progress, g.target)}
          <small>${g.reached ? "Reached! Hand it out, then start a new one." : `${g.progress} of ${g.target} points together since ${esc(whenText(g.since))}`}</small></span></div>`
      : `<p class="empty">No family goal right now.</p>`;
    const form = editing
      ? `<form class="edit" data-goal-form>
          <div class="inline">
            <label class="field"><span>Emoji</span><input name="emoji" maxlength="8" value="${esc(g?.emoji || "")}" placeholder="🍕" style="width:70px"></label>
            <label class="field grow"><span>What it's for</span><input name="name" maxlength="60" required value="${esc(g?.name || "")}" placeholder="Pizza night"></label>
            <label class="field"><span>Points together</span><input type="number" name="target" min="1" max="10000" required value="${esc(g?.target || "")}" placeholder="200" style="width:110px"></label>
          </div>
          ${g ? `<label class="check"><input type="checkbox" name="restart"> Start counting again from now</label>` : ""}
          <div class="form-actions"><button class="btn primary" type="submit">Save goal</button><button class="btn" type="button" data-cancel>Cancel</button></div></form>`
      : `<div class="form-actions"><button class="btn primary" data-new="family_goal">${g ? (g.reached ? "Start a new goal" : "Change the goal") : "Set a family goal"}</button>${g ? `<button class="btn bad" data-goal-remove>Remove</button>` : ""}</div>`;
    return `<div class="card"><h2>Family goal</h2>
      <p class="muted">Something the whole family works toward together. Points from everyone's chores count toward it; nobody spends any.</p>
      ${status}${form}</div>`;
  }

  _renderRewards() {
    const d = this._data;
    const edit = this._edit;
    const rows = d.rewards.length
      ? `<ul class="rows">${d.rewards
          .map((r) => `<li><span class="grow">${r.emoji ? `${esc(r.emoji)} ` : ""}<b>${esc(r.name)}</b>
              <small>${this._rewardLine(r)}</small></span>
              <button class="btn" data-edit="rewards" data-id="${esc(r.id)}">Edit</button>
              <button class="btn bad" data-delete="rewards" data-id="${esc(r.id)}">Delete</button></li>`)
          .join("")}</ul>`
      : `<p class="empty">No rewards yet.</p>`;
    const form = edit?.collection === "rewards" ? this._rewardForm(edit.item) : `<button class="btn primary" data-new="rewards">Add a reward</button>`;
    const b = d.bonus || {};
    return `${this._familyGoalCard()}<div class="card"><h2>Rewards</h2>${rows}${form}</div>
      <div class="card"><h2>Bonus points</h2>
        <form class="edit" data-bonus>
          <label class="field"><span>All of their own chores done for the day</span>
            <span><input type="number" name="bonus_all_done" min="0" max="10000" value="${esc(b.all_done || 0)}" style="width:100px"> extra points</span>
            <small>Only their own chores count, not ones up for grabs. Set 0 for no points: the day still counts for their streak.</small></label>
          <div class="field"><span>A streak: days in a row with all of their own chores done</span>
            <span class="inline">Every <input type="number" name="streak_days" min="0" max="365" value="${esc(b.streak_days || 0)}" aria-label="Days in a row" style="width:80px"> days in a row:
            <input type="number" name="streak_bonus" min="0" max="10000" value="${esc(b.streak || 0)}" aria-label="Streak bonus points" style="width:100px"> extra points</span>
            <small>For example every 7 days. Chores up for grabs don't count, and a day with none of their own chores doesn't break it. The Family dashboard shows each streak with 🔥.</small></div>
          <small class="muted">0 turns a bonus off. A bonus goes away when its chore is undone or marked <b>Didn't happen</b>.</small>
          <div class="form-actions"><button class="btn primary" type="submit">Save bonuses</button></div>
        </form></div>`;
  }

  _rewardForm(item) {
    const tvs = this._choices?.tvs || [];
    const speakers = this._choices?.speakers || [];
    const r = item || { name: "", points: 20, kind: tvs.length ? "tv_time" : "custom", minutes: 30, tv: tvs[0]?.id, whole_home: false };
    const kind = this._rewardKind || r.kind;
    const tvFields = kind === "tv_time"
      ? (tvs.length
        ? `<div class="inline">
            <label class="field"><span>TV</span><select name="tv">${tvs.map((t) => `<option value="${esc(t.id)}" ${t.id === r.tv ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></label>
            <label class="field"><span>Minutes</span><input type="number" name="minutes" min="1" max="240" value="${esc(r.minutes || 30)}"></label>
          </div>
          <label class="check"><input type="checkbox" name="whole_home" ${r.whole_home ? "checked" : ""}> Give the whole home the same time too</label>
          <small class="muted">The TV time is given in TV Mgmt as soon as the reward is picked.</small>`
        : `<p class="error">TV time needs TV Mgmt with at least one TV set up.</p>`)
      : kind === "music_time"
        ? (speakers.length
          ? `<div class="inline">
              <label class="field"><span>Speaker</span><select name="speaker">${speakers.map((t) => `<option value="${esc(t.id)}" ${t.id === r.speaker ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></label>
              <label class="field"><span>Minutes</span><input type="number" name="minutes" min="1" max="240" value="${esc(r.minutes || 30)}"></label>
            </div>
            <label class="check"><input type="checkbox" name="whole_home" ${r.whole_home ? "checked" : ""}> Give the whole home the same time too</label>
            <small class="muted">The listening time is given in Media Mgmt as soon as the reward is picked. The whole home's time needs Media Mgmt 1.5.0 or newer.</small>`
          : `<p class="error">Music time needs Media Mgmt with at least one speaker set up.</p>`)
        : `<small class="muted">A parent hands it out; it shows under To check until then.</small>`;
    return `<form class="edit" data-form="rewards" data-id="${esc(r.id || "")}">
      <div class="inline">
        <label class="field"><span>Reward</span><input type="text" name="name" value="${esc(r.name)}" required placeholder="30 minutes of TV"></label>
        <label class="field"><span>Emoji</span><input type="text" name="emoji" value="${esc(r.emoji || "")}" size="3" placeholder="📺"></label>
        <label class="field"><span>Costs</span><input type="number" name="points" min="0" max="10000" value="${esc(r.points)}"></label>
        <label class="field"><span>How often</span><select name="limit">${LIMITS.map((l) => `<option value="${l.id}" ${(r.limit || "") === l.id ? "selected" : ""}>${l.label}</option>`).join("")}</select></label>
        <label class="field"><span>What it is</span><select name="kind" data-reward-kind>
          <option value="tv_time" ${kind === "tv_time" ? "selected" : ""}>TV time</option>
          <option value="music_time" ${kind === "music_time" ? "selected" : ""}>Music time</option>
          <option value="custom" ${kind === "custom" ? "selected" : ""}>Something else</option></select></label>
      </div>
      ${tvFields}
      <div class="field"><span>Who can get it</span>${this._rewardWho(r.members)}</div>
      <div class="form-actions"><button class="btn primary" type="submit">Save reward</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  _renderHome() {
    const d = this._data;
    const edit = this._edit;
    const last = d.controls.length - 1;
    const rows = d.controls.length
      ? `<ul class="rows">${d.controls
          .map((c, i) => {
            const domain = c.entity_id.split(".")[0];
            const icon = c.emoji ? `${esc(c.emoji)} ` : `<ha-icon icon="${esc(DOMAIN_ICONS[domain] || "mdi:eye")}"></ha-icon> `;
            const asks = c.confirm && c.kind !== "view" ? " · asks first" : "";
            return `<li><span class="grow">${icon}<b>${esc(c.label)}</b>
              <small>${esc(KIND_TEXT[c.kind] || "")} · ${esc(c.members?.length ? `Shown to ${this._whoText(c.members)}` : "Shown to everyone")}${asks}</small></span>
              <button class="btn" data-move="controls" data-id="${esc(c.id)}" data-offset="-1" ${i === 0 ? "disabled" : ""} aria-label="Move up">↑</button>
              <button class="btn" data-move="controls" data-id="${esc(c.id)}" data-offset="1" ${i === last ? "disabled" : ""} aria-label="Move down">↓</button>
              <button class="btn" data-edit="controls" data-id="${esc(c.id)}">Edit</button>
              <button class="btn bad" data-delete="controls" data-id="${esc(c.id)}">Remove</button></li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">Nothing yet. Add scenes, lights, blinds or anything else the family should be able to use or see.</p>`;
    const form = edit?.collection === "controls" ? this._controlForm(edit.item) : `<button class="btn primary" data-new="controls">Add to the dashboard</button>`;
    return `<div class="card"><h2>Home</h2>
      <p class="muted">These show on the Family dashboard under <b>Home</b>. Anyone at the Family dashboard can use them, so only add what the kids may use. Sensors, thermostats and the weather are only shown.</p>
      ${rows}${form}</div>`;
  }

  _entityOptions(query, selected) {
    const q = (query || "").trim().toLowerCase();
    const groups = new Map();
    for (const e of this._choices?.entities || []) {
      if (q && e.entity_id !== selected && !e.name.toLowerCase().includes(q) && !e.entity_id.includes(q)) continue;
      const label = DOMAIN_LABELS[e.domain] || e.domain;
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(e);
    }
    if (!groups.size) return `<option value="" disabled>Nothing matches</option>`;
    return [...groups]
      .map(([label, items]) => `<optgroup label="${esc(label)}">${items
        .map((e) => `<option value="${esc(e.entity_id)}" ${e.entity_id === selected ? "selected" : ""}>${esc(e.name)}</option>`)
        .join("")}</optgroup>`)
      .join("");
  }

  _controlForm(item) {
    const c = item || { entity_id: "", name: "", emoji: "", members: [], confirm: false };
    return `<form class="edit" data-form="controls" data-id="${esc(c.id || "")}">
      <label class="field"><span>What to show</span>
        <input type="text" data-filter placeholder="Search" aria-label="Search">
        <select name="entity_id" size="8" required>${this._entityOptions("", c.entity_id)}</select></label>
      <div class="inline">
        <label class="field"><span>Name</span><input type="text" name="name" value="${esc(c.name || "")}" placeholder="Its own name"></label>
        <label class="field"><span>Emoji</span><input type="text" name="emoji" value="${esc(c.emoji || "")}" size="3" placeholder="🎬"></label>
      </div>
      <div class="field"><span>Who sees it</span>${this._whoChecks(c.members).replace("anyone can do it", "everyone sees it")}</div>
      <label class="check"><input type="checkbox" name="confirm" ${c.confirm ? "checked" : ""}> Ask "Are you sure?" first (good for locks and doors)</label>
      <div class="form-actions"><button class="btn primary" type="submit">Save</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  _renderMeals() {
    const d = this._data;
    const rows = (d.meals || [])
      .map((day, i) => {
        const date = new Date(`${day.date}T12:00:00`);
        const label = i < 2 ? `${dayText(day.date, i)} · ${WEEKDAYS_LONG[(date.getDay() + 6) % 7]}` : `${WEEKDAYS_LONG[(date.getDay() + 6) % 7]} ${date.getDate()}`;
        return `<form class="meal-row" data-meals="${esc(day.date)}">
          <b class="meal-day">${esc(label)}</b>
          ${MEALS.map(([k, name]) => `<label class="field"><span>${name}</span><input type="text" name="${k}" maxlength="80" value="${esc(day[k] || "")}"></label>`).join("")}
          <button class="btn" type="submit">Save</button></form>`;
      })
      .join("");
    return `<div class="card"><h2>Meals for the week</h2>
      <p class="muted">What's for breakfast, lunch and dinner. Today's and tomorrow's show on the Family dashboard. Leave a meal empty to leave it out.</p>
      ${rows}</div>`;
  }

  _renderNotes() {
    const d = this._data;
    const notes = d.notes || [];
    const rows = notes.length
      ? `<ul class="rows">${notes
          .map((n) => {
            const m = this._memberById(n.member);
            return `<li>${m ? this._avatar(m, true) : ""}<span class="grow">${esc(n.text)}<small>${esc(whenText(n.at))}${n.by ? ` · by ${esc(n.by)}` : ""}${m ? ` · for ${esc(m.name)}` : ""}${n.until ? ` · until ${esc(dayText(n.until, -1))}` : ""}</small></span>
              <button class="btn bad" data-note-remove="${esc(n.id)}">Take down</button></li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No notes on the board.</p>`;
    const people = d.members.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("");
    return `<div class="card"><h2>Notes</h2>
      <p class="muted">Short notes and reminders on the Family dashboard. Anyone can put one up there too; a parent's note can only be taken down by a parent.</p>
      ${rows}
      <form class="edit" data-note-form>
        <label class="field"><span>Note</span><input type="text" name="text" maxlength="200" required placeholder="Library books due Friday"></label>
        <div class="inline">
          <label class="field"><span>For</span><select name="member_id"><option value="">Everyone</option>${people}</select></label>
          <label class="field"><span>Show until (optional)</span><input type="date" name="until"></label>
        </div>
        <div class="form-actions"><button class="btn primary" type="submit">Put it up</button></div>
      </form></div>`;
  }

  _allowanceCard() {
    const st = this._data.settings || {};
    const day = st.allowance_day ?? 6;
    const hour = st.allowance_hour ?? 8;
    const hours = Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${h === hour ? "selected" : ""}>${esc(timeText(`${String(h).padStart(2, "0")}:00`))}</option>`).join("");
    return `<div class="card"><h2>Allowance and money</h2>
      <p class="muted">Give each family member points every week: set how many when you edit them, under Family. Add what a point is worth to show their points as money too.</p>
      <form class="edit" data-allowance>
        <div class="inline">
          <label class="field"><span>Given on</span><select name="allowance_day">${WEEKDAYS_LONG.map((name, i) => `<option value="${i}" ${i === day ? "selected" : ""}>${name}</option>`).join("")}</select></label>
          <label class="field"><span>At</span><select name="allowance_hour">${hours}</select></label>
          <label class="field"><span>One point is worth</span><input type="number" name="point_value" min="0" max="100" step="0.01" value="${esc(st.point_value ?? "")}" placeholder="No money value" style="width:130px"></label>
          <label class="field"><span>Money sign</span><input type="text" name="currency" maxlength="4" value="${esc(st.currency || "")}" placeholder="$" style="width:70px"></label>
        </div>
        <div class="form-actions"><button class="btn primary" type="submit">Save</button></div>
      </form></div>`;
  }

  _calendarCard() {
    const st = this._data.settings || {};
    const picked = new Map((st.calendars || []).map((c) => [c.entity_id, c.member || ""]));
    const calendars = this._choices?.calendars || [];
    const members = this._data.members;
    const rows = calendars.length
      ? `<ul class="rows">${calendars
          .map((c) => `<li><label class="check grow"><input type="checkbox" name="calendar" value="${esc(c.entity_id)}" ${picked.has(c.entity_id) ? "checked" : ""}> ${esc(c.name)}</label>
            <select name="member:${esc(c.entity_id)}" aria-label="Whose calendar is ${esc(c.name)}"><option value="">Everyone's</option>${members.map((m) => `<option value="${esc(m.id)}" ${picked.get(c.entity_id) === m.id ? "selected" : ""}>${esc(m.name)}'s</option>`).join("")}</select></li>`)
          .join("")}</ul>`
      : `<p class="empty">No calendars yet. Add one to Home Assistant, such as Local Calendar or Google Calendar.</p>`;
    return `<div class="card"><h2>Today's calendar</h2>
      <p class="muted">Today's events from these calendars show on the Family dashboard. A calendar for one person shows on their own page; everyone's shows on every page.</p>
      <form class="edit" data-calendars>${rows}
        ${calendars.length ? `<div class="form-actions"><button class="btn primary" type="submit">Save</button></div>` : ""}</form></div>`;
  }

  _voiceCard() {
    const voices = this._choices?.voices || [];
    const current = this._data.settings?.reminder_tts || "";
    const body = voices.length
      ? `<form class="edit" data-voice-form><div class="inline"><label class="field"><span>Voice</span><select name="reminder_tts"><option value="">Off</option>${voices.map((v) => `<option value="${esc(v.entity_id)}" ${current === v.entity_id ? "selected" : ""}>${esc(v.name)}</option>`).join("")}</select></label>
          <button class="btn" type="submit" style="align-self:end">Save</button></div></form>`
      : `<p class="empty">No text-to-speech in Home Assistant yet. Add one, such as Google Translate text-to-speech or Piper.</p>`;
    return `<div class="card"><h2>Speaker reminders</h2>
      <p class="muted">A chore can be said out loud on a speaker at a set time while someone still has it to do. Pick the voice here, then set the time and speakers on each chore.</p>${body}</div>`;
  }

  _renderMembers() {
    const d = this._data;
    const edit = this._edit;
    const rows = d.members.length
      ? `<ul class="rows">${d.members
          .map((m) => `<li>${this._avatar(m, true)}<span class="grow"><b>${esc(m.name)}</b> · ${pts(m.points)}${d.money ? ` (${esc(money(m.points, d.money))})` : ""}${m.allowance ? ` · +${m.allowance} a week` : ""}
              <small>${m.person ? `Linked to ${esc(this._choices?.people.find((p) => p.entity_id === m.person)?.name || m.person)}` : "Not linked to a Home Assistant person"}</small></span>
              <form class="inline" data-adjust="${esc(m.id)}">
                <input type="number" name="points" placeholder="± points" aria-label="Points for ${esc(m.name)}" style="width:100px">
                <input type="text" name="reason" placeholder="Why (optional)" aria-label="Why">
                <button class="btn" type="submit">Change points</button></form>
              <button class="btn" data-edit="members" data-id="${esc(m.id)}">Edit</button>
              <button class="btn bad" data-delete="members" data-id="${esc(m.id)}">Remove</button></li>`)
          .join("")}</ul>`
      : `<p class="empty">No family members yet.</p>`;
    const form = edit?.collection === "members" ? this._memberForm(edit.item) : `<button class="btn primary" data-new="members">Add a family member</button>`;
    return `<div class="card"><h2>Family</h2>
      <p class="muted">Link someone to their Home Assistant person to use its picture. If they log in to Home Assistant, the Family dashboard opens on their own page.</p>
      ${rows}${form}</div>
      ${this._allowanceCard()}
      ${this._calendarCard()}
      ${this._voiceCard()}
      ${this._sectionsCard()}
      <div class="card"><h2>Shared screen</h2>
        <p class="muted">Home Assistant only offers dashboards as a login's default, not sidebar pages like this one. Make a dashboard that shows the Family dashboard, then log in on the shared screen and pick <b>${esc(DASHBOARD_TITLE)}</b> under your profile's <b>Dashboard</b>.</p>
        <p class="muted">It has a <b>Home</b> tab for everyone and a tab for each family member, and the tabs follow when you add, rename or remove someone here. You can add your own tabs and cards to it in Home Assistant; they're kept. You can also add the <b>Family</b> card to any dashboard yourself, for everyone or for one person.</p>
        <button class="btn primary" data-make-dashboard ${this._busy ? "disabled" : ""}>${this._hasDashboard ? "Update the Family dashboard" : "Make a Family dashboard"}</button></div>`;
  }

  // Every Parents card folds by its heading. Which are folded is kept per
  // screen (localStorage, with a copy in memory for when that isn't
  // available), and a folded card stays folded through every redraw until
  // its heading is tapped.
  _closedCards() {
    if (!this._closed) {
      try {
        this._closed = JSON.parse(localStorage.getItem("family-parents-closed") || "[]");
      } catch (err) {
        this._closed = [];
      }
      if (!Array.isArray(this._closed)) this._closed = [];
    }
    return this._closed;
  }

  _foldCards() {
    const closed = this._closedCards();
    for (const card of this.shadowRoot.querySelectorAll("main .card")) {
      const head = card.querySelector(":scope > h2");
      if (!head) continue;
      const key = head.textContent.replace(/\s+\d+$/, "").trim();
      head.dataset.fold = key;
      head.setAttribute("role", "button");
      head.setAttribute("tabindex", "0");
      const isClosed = closed.includes(key);
      card.classList.toggle("folded", isClosed);
      head.setAttribute("aria-expanded", String(!isClosed));
    }
  }

  _toggleFold(key, open = null) {
    let closed = this._closedCards();
    const isClosed = closed.includes(key);
    if (open === true && !isClosed) return;
    closed = isClosed ? closed.filter((k) => k !== key) : [...closed, key];
    this._closed = closed;
    try {
      localStorage.setItem("family-parents-closed", JSON.stringify(closed));
    } catch (err) {
      // Kept in memory: it stays folded until the page is opened again.
    }
    for (const head of this.shadowRoot.querySelectorAll("main .card > h2")) {
      if (head.dataset.fold !== key) continue;
      const card = head.parentElement;
      card.classList.toggle("folded", closed.includes(key));
      head.setAttribute("aria-expanded", String(!closed.includes(key)));
    }
  }

  // The order of the Family dashboard's sections, moved up and down here.
  _sectionsCard() {
    const order = sectionOrder(this._data.section_order);
    const names = Object.fromEntries(SECTIONS);
    return `<div class="card"><h2>Family dashboard sections</h2>
      <p class="muted">The order the sections show in, on every screen.</p>
      <label class="check"><input type="checkbox" data-hide-empty ${this._data.hide_empty_sections ? "checked" : ""} ${this._busy ? "disabled" : ""}> Hide sections with nothing in them</label>
      <p class="muted">For example Up for grabs when there's nothing up for grabs, or Today on a day with no events. Notes always shows, so a note can be added.</p>
      <ul class="rows">${order
        .map((key, i) => `<li><span class="grow">${esc(names[key])}</span>
          <button class="btn" data-section-move="${key}" data-offset="-1" ${i === 0 || this._busy ? "disabled" : ""} aria-label="Move ${esc(names[key])} up">↑</button>
          <button class="btn" data-section-move="${key}" data-offset="1" ${i === order.length - 1 || this._busy ? "disabled" : ""} aria-label="Move ${esc(names[key])} down">↓</button></li>`)
        .join("")}</ul></div>`;
  }

  async _makeDashboard() {
    if (this._busy) return;
    this._busy = true;
    try {
      const made = await this._syncDashboard(true);
      this._toast(made ? `Made ${DASHBOARD_TITLE}. Pick it as the shared screen's default dashboard.` : `Updated ${DASHBOARD_TITLE}.`);
    } catch (err) {
      this._toast(err?.message || String(err), true);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  // Makes the Family dashboard (when `make` is set) or brings its tabs up to
  // date with the family members. Returns true when it was made.
  async _syncDashboard(make) {
    const dashboards = await this._ws({ type: "lovelace/dashboards/list" });
    const exists = dashboards.some((d) => d.url_path === DASHBOARD_PATH);
    this._hasDashboard = exists;
    if (!exists && !make) return false;
    let config = { title: DASHBOARD_TITLE, views: [] };
    if (exists) {
      try {
        config = await this._ws({ type: "lovelace/config", url_path: DASHBOARD_PATH });
      } catch (err) {
        // Made but never saved: start from nothing.
        if (err?.code !== "config_not_found") throw err;
      }
    } else {
      await this._ws({
        type: "lovelace/dashboards/create",
        url_path: DASHBOARD_PATH,
        title: DASHBOARD_TITLE,
        icon: "mdi:home-heart",
        mode: "storage",
        require_admin: false,
        // The Family page is in the sidebar already.
        show_in_sidebar: false,
      });
    }
    const views = familyViews(config.views, this._data.members);
    if (exists && JSON.stringify(views) === JSON.stringify(config.views)) return false;
    await this._ws({ type: "lovelace/config/save", url_path: DASHBOARD_PATH, config: { ...config, views } });
    this._hasDashboard = true;
    return !exists;
  }

  // After a family member is added, renamed or removed.
  async _followMembers() {
    try {
      await this._syncDashboard(false);
    } catch (err) {
      this._toast(`Couldn't update ${DASHBOARD_TITLE}: ${err?.message || err}`, true);
    }
  }

  _memberForm(item) {
    const m = item || { name: "", person: "", emoji: "", color: "", allowance: 0 };
    // Someone already linked to another family member isn't offered again.
    const taken = new Set(this._data.members.filter((x) => x.person && x.id !== m.id).map((x) => x.person));
    const people = (this._choices?.people || []).filter((p) => !taken.has(p.entity_id));
    return `<form class="edit" data-form="members" data-id="${esc(m.id || "")}">
      <div class="inline">
        <label class="field"><span>Name</span><input type="text" name="name" value="${esc(m.name)}" required></label>
        <label class="field"><span>Emoji</span><input type="text" name="emoji" value="${esc(m.emoji || "")}" size="3" placeholder="🦖"></label>
        <label class="field"><span>Color</span><input type="color" name="color" value="${esc(m.color || "#3F51B5")}"></label>
        <label class="field"><span>Allowance (points a week)</span><input type="number" name="allowance" min="0" max="10000" value="${esc(m.allowance || 0)}" style="width:100px"></label>
        <label class="field"><span>Home Assistant person</span><select name="person" data-person><option value="">None</option>${people.map((p) => `<option value="${esc(p.entity_id)}" ${p.entity_id === m.person ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
      </div>
      <div class="form-actions"><button class="btn primary" type="submit">Save</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  // ------------------------------------------------------------------ events

  async _ws(msg) {
    return this._hass.callWS(msg);
  }

  _onClick(ev) {
    const toggle = ev.target.closest("[data-eligible-toggle]");
    if (toggle) {
      ev.preventDefault();
      this._toggleEligible(toggle);
      return;
    }
    // A tap outside the people list closes it. Ticks inside stay open.
    if (!ev.target.closest("[data-eligible]")) this._closeEligible();
    // A Parents card's heading folds it (buttons inside it don't).
    const fold = ev.target.closest("[data-fold]");
    if (fold && !ev.target.closest("button")) {
      this._toggleFold(fold.dataset.fold);
      return;
    }
    // A button in a folded card's heading (Add, say) opens the card first,
    // so what it shows can be seen.
    if (fold && fold.parentElement?.classList.contains("folded")) this._toggleFold(fold.dataset.fold, true);
    const el = ev.target.closest("button, .sheet-bg");
    if (!el) return;
    const ds = el.dataset;
    if ("close" in ds) {
      // A tap outside the sheet, or Cancel, closes it.
      if (el.classList.contains("sheet-bg") && ev.target !== el) return;
      this._sheet = null;
      this._renderOverlay();
      return;
    }
    if (ds.member) {
      if (this._pinnedMember()) return;
      this._member = this._member === ds.member ? null : ds.member;
      this._render();
    } else if (ds.sectionToggle) {
      const key = ds.sectionToggle;
      this._setSection(key, this._sectionMode(key) === "closed" ? "first" : "closed");
    } else if (ds.more) {
      this._setSection(ds.more, this._sectionMode(ds.more) === "all" ? "first" : "all");
    } else if ("makeDashboard" in ds) {
      this._makeDashboard();
    } else if ("noteNew" in ds) {
      this._sheet = { type: "note", member: this._member };
      this._renderOverlay();
    } else if (ds.noteRemove) {
      this._call({ type: `${DOMAIN}/note/remove`, note_id: ds.noteRemove }, "Note taken down.");
    } else if (ds.undo) {
      this._undo(ds.undo);
    } else if (ds.control) {
      this._useControl(ds.control);
    } else if (ds.move) {
      this._call({ type: `${DOMAIN}/move`, collection: ds.move, item_id: ds.id, offset: Number(ds.offset) }, "Moved.");
    } else if (ds.chore) {
      // On someone's page, or a chore only one person can do: tick it off
      // straight away (the toast can undo it). Otherwise ask who did it.
      const chore = this._data.chores.find((c) => c.id === ds.chore);
      const only = chore?.can?.length === 1 ? chore.can[0] : null;
      const who = this._member && chore?.can?.includes(this._member) ? this._member : only;
      this._sheet = { type: "chore", id: ds.chore, member: who, quick: !!who };
      if (who) this._confirm();
      else this._renderOverlay();
    } else if (ds.routine) {
      this._sheet = { type: "routine", id: ds.routine, member: this._member || null };
      const r = (this._data.routines || []).find((x) => x.id === ds.routine);
      // Only one person does it: no need to ask who.
      if (!this._sheet.member && r?.who.length === 1) this._sheet.member = r.who[0];
      this._renderOverlay();
    } else if (ds.routineWho) {
      this._sheet = { ...this._sheet, member: ds.routineWho };
      this._renderOverlay();
    } else if (ds.routineStep !== undefined) {
      this._routineStep(Number(ds.routineStep));
    } else if (ds.reward) {
      this._sheet = { type: "reward", id: ds.reward, member: this._member };
      this._renderOverlay();
    } else if (ds.sectionMove) {
      const order = sectionOrder(this._data.section_order);
      const from = order.indexOf(ds.sectionMove);
      const to = from + Number(ds.offset);
      if (to < 0 || to >= order.length) return;
      [order[from], order[to]] = [order[to], order[from]];
      this._call({ type: `${DOMAIN}/settings`, section_order: order }, "Moved.");
    } else if ("days" in ds) {
      this._sheet = { type: "days", member: this._member };
      this._renderOverlay();
    } else if ("togetherStart" in ds) {
      const s = this._sheet;
      this._sheet = { type: "together", id: s.id, with: s.member ? [s.member] : [] };
      this._renderOverlay();
    } else if (ds.together) {
      const s = this._sheet;
      s.with = s.with.includes(ds.together) ? s.with.filter((id) => id !== ds.together) : [...s.with, ds.together];
      this._renderOverlay();
    } else if (ds.approve) {
      this._call({ type: `${DOMAIN}/approve`, group_id: ds.approve, approved: ds.yes === "1" }, ds.yes === "1" ? "Said yes." : "Said no. The points are back.");
    } else if (ds.sheetMember) {
      this._sheet = { ...this._sheet, member: ds.sheetMember };
      this._renderOverlay();
    } else if ("goal" in ds) {
      this._setGoal(ds.goal || null);
    } else if ("confirm" in ds) {
      this._confirm();
    } else if (ds.tab) {
      this._tab = ds.tab;
      this._edit = null;
      this._render();
    } else if ("goalRemove" in ds) {
      this._call({ type: `${DOMAIN}/settings`, family_goal: null }, "Goal removed.");
    } else if (ds.quick !== undefined && ds.memberId) {
      const button = (this._data.settings?.quick_points || [])[Number(ds.quick)];
      const m = this._memberById(ds.memberId);
      if (!button || !m || this._busy) return;
      const sign = button.points > 0 ? "+" : "−";
      this._call({ type: `${DOMAIN}/adjust`, member_id: m.id, points: button.points, reason: `${button.emoji ? `${button.emoji} ` : ""}${button.label}` }, `${m.name}: ${sign}${pts(Math.abs(button.points))} for ${button.label}`);
    } else if (ds.new) {
      this._edit = { collection: ds.new, item: null };
      this._rewardKind = null;
      this._render();
    } else if (ds.edit) {
      const list = ds.edit === "chores" ? this._data.all_chores : ds.edit === "routines" ? this._data.all_routines : this._data[ds.edit];
      this._edit = { collection: ds.edit, item: list.find((x) => x.id === ds.id) };
      this._rewardKind = null;
      this._render();
    } else if ("cancel" in ds) {
      this._edit = null;
      this._render();
    } else if (ds.delete) {
      const what = { controls: "this from the Family dashboard", chores: "this chore", rewards: "this reward", members: "this family member and their points", todo_lists: "this to-do list from Family (the list itself stays)" }[ds.delete];
      if (!window.confirm(`Remove ${what}?`)) return;
      this._call({ type: `${DOMAIN}/delete`, collection: ds.delete, item_id: ds.id }, "Removed.").then((ok) => {
        if (ok && ds.delete === "members") this._followMembers();
      });
    } else if (ds.review) {
      const msg = { type: `${DOMAIN}/review`, entry_id: ds.review, approved: ds.approved === "1" };
      const box = this.shadowRoot.querySelector(`[data-penalty-for="${CSS.escape(ds.review)}"]`);
      if (!msg.approved && box && box.value.trim() !== "") msg.penalty = Math.max(0, Math.round(Number(box.value) || 0));
      this._call(msg, msg.approved ? "Checked." : "Points taken back.");
    } else if (ds.given) {
      this._call({ type: `${DOMAIN}/given`, entry_id: ds.given }, "Marked as handed out.");
    }
  }

  _onChange(ev) {
    if (ev.target.dataset.itemSkip !== undefined) {
      ev.target.closest("li")?.classList.toggle("skipped", ev.target.checked);
      return;
    }
    if (ev.target.name === "members" && ev.target.closest("[data-eligible]")) {
      this._syncEligible(ev.target.closest("[data-eligible]"));
      return;
    }
    if (ev.target.dataset.turns !== undefined) {
      const fields = ev.target.closest("form").querySelector("[data-turn-fields]");
      if (fields) fields.hidden = !ev.target.checked;
      return;
    }
    if (ev.target.dataset.repeat !== undefined) {
      const days = ev.target.closest("form").querySelector("[data-days-field]");
      if (days) days.hidden = ev.target.value !== "after_days";
      return;
    }
    if (ev.target.dataset.person !== undefined) {
      // An empty name takes the person's first name.
      const name = ev.target.closest("form").querySelector('input[name="name"]');
      const person = this._choices?.people.find((p) => p.entity_id === ev.target.value);
      if (name && !name.value.trim() && person) name.value = person.name.split(" ")[0];
      return;
    }
    if (ev.target.dataset.hideEmpty !== undefined) {
      this._call({ type: `${DOMAIN}/settings`, hide_empty_sections: ev.target.checked }, "Saved.");
      return;
    }
    if (ev.target.dataset.autoCheck !== undefined) {
      this._call({ type: `${DOMAIN}/settings`, auto_check: ev.target.value || null }, "Saved.");
      return;
    }
    if (ev.target.dataset.rewardKind !== undefined) {
      // Show the TV fields for TV time, keeping what's typed so far,
      // including who the reward is for.
      const form = ev.target.closest("form");
      const item = this._rewardDraft(form);
      this._rewardKind = ev.target.value;
      this._edit = { ...this._edit, item };
      this._render();
    }
  }

  // The reward form, as it will be saved. Every person ticked is everyone
  // (members null). A shorter list is only those people. Nobody ticked is [].
  _rewardDraft(form) {
    const v = this._formValues(form);
    const item = { ...(this._edit?.item || {}), ...v };
    item.members = this._rewardMembers(v);
    item.whole_home = !!v.whole_home;
    return item;
  }

  _onInput(ev) {
    if (ev.target.dataset.filter === undefined) return;
    // Narrow the entity list as a parent types, keeping what's picked.
    const select = ev.target.closest("form").querySelector('select[name="entity_id"]');
    select.innerHTML = this._entityOptions(ev.target.value, select.value);
  }

  _formValues(form) {
    const data = new FormData(form);
    const out = {};
    for (const [key, value] of data.entries()) {
      if (key === "members" || key === "days" || key === "notify_targets" || key === "remind_speakers") (out[key] ||= []).push(value);
      else out[key] = value;
    }
    return out;
  }

  async _onSubmit(ev) {
    ev.preventDefault();
    const form = ev.target;
    if (form.dataset.penaltySetting !== undefined) {
      const value = Math.max(0, Math.round(Number(this._formValues(form).penalty) || 0));
      return this._call({ type: `${DOMAIN}/settings`, penalty: value }, "Saved.");
    }
    if (form.dataset.phones !== undefined) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/settings`, notify_targets: v.notify_targets || [], notify_done: !!v.notify_done, notify_rewards: !!v.notify_rewards, weekly_summary: !!v.weekly_summary }, "Saved.");
    }
    if (form.dataset.goalForm !== undefined) {
      const v = this._formValues(form);
      const reached = this._data.family_goal?.reached;
      const ok = await this._call({ type: `${DOMAIN}/settings`, family_goal: { name: v.name, emoji: v.emoji || null, target: Math.round(Number(v.target) || 0) }, restart_goal: !!v.restart || !!reached }, "Saved.");
      if (ok) {
        this._edit = null;
        this._render();
      }
      return;
    }
    if (form.dataset.voiceForm !== undefined) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/settings`, reminder_tts: v.reminder_tts || null }, "Saved.");
    }
    if (form.dataset.quickForm !== undefined) {
      const quick_points = [...form.querySelectorAll("li")]
        .map((li) => ({
          label: li.querySelector('[name="label"]').value.trim(),
          emoji: li.querySelector('[name="emoji"]').value.trim(),
          points: Math.round(Number(li.querySelector('[name="points"]').value) || 0),
        }))
        .filter((b) => b.label && b.points);
      const ok = await this._call({ type: `${DOMAIN}/settings`, quick_points }, "Saved.");
      if (ok) {
        this._edit = null;
        this._render();
      }
      return;
    }
    if (form.dataset.noteForm !== undefined) {
      const v = this._formValues(form);
      if (!String(v.text || "").trim()) return this._toast("Write something for the note.", true);
      const ok = await this._call({ type: `${DOMAIN}/note/add`, text: v.text, member_id: v.member_id || null, until: v.until || null }, "Note put up.");
      if (ok) {
        this._sheet = null;
        this._renderOverlay();
      }
      return;
    }
    if (form.dataset.meals) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/meals`, date: form.dataset.meals, breakfast: v.breakfast || "", lunch: v.lunch || "", dinner: v.dinner || "" }, "Meals saved.");
    }
    if (form.dataset.allowance !== undefined) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/settings`, allowance_day: Number(v.allowance_day), allowance_hour: Number(v.allowance_hour), point_value: v.point_value === "" ? null : Number(v.point_value), currency: v.currency || "" }, "Saved.");
    }
    if (form.dataset.calendars !== undefined) {
      const calendars = [...form.querySelectorAll('input[name="calendar"]')]
        .filter((el) => el.checked)
        .map((el) => ({ entity_id: el.value, member: form.querySelector(`select[name="member:${el.value}"]`)?.value || null }));
      return this._call({ type: `${DOMAIN}/settings`, calendars }, "Saved.");
    }
    if (form.dataset.bonus !== undefined) {
      const v = this._formValues(form);
      const number = (x) => Math.max(0, Math.round(Number(x) || 0));
      return this._call({ type: `${DOMAIN}/settings`, bonus_all_done: number(v.bonus_all_done), streak_days: number(v.streak_days), streak_bonus: number(v.streak_bonus) }, "Bonuses saved.");
    }
    if (form.dataset.adjust) {
      const values = this._formValues(form);
      const points = Number(values.points);
      if (!Number.isInteger(points) || points === 0) return this._toast("Enter a whole number of points, like 5 or -5.", true);
      return this._call({ type: `${DOMAIN}/adjust`, member_id: form.dataset.adjust, points, reason: values.reason || undefined }, "Points changed.");
    }
    const collection = form.dataset.form;
    const v = this._formValues(form);
    let item;
    if (collection === "chores") {
      item = { remind_time: v.remind_time || null, remind_speakers: v.remind_speakers || [], name: v.name, emoji: v.emoji, points: Number(v.points || 0), penalty: v.penalty === "" ? null : Number(v.penalty), repeat: v.repeat, repeat_days: Number(v.repeat_days || 1), todo_list: v.todo_list || null, due_only: !!v.due_only && !!v.todo_list, members: v.members || [], grab: !!v.grab, enabled: !!v.enabled, days: (v.days || []).map(Number), from_time: v.from_time || null, until_time: v.until_time || null, turns: !!v.turns, turn_every: v.turn_every || "time", turn_first: v.turn_first || null };
    } else if (collection === "routines") {
      item = { name: v.name, emoji: v.emoji, points: Number(v.points || 0), members: v.members || [], steps: (v.steps || "").split("\n").map((x) => x.trim()).filter(Boolean), days: (v.days || []).map(Number), from_time: v.from_time || null, until_time: v.until_time || null, enabled: !!v.enabled };
    } else if (collection === "rewards") {
      // All ticked: anyone, including people added later. A shorter list:
      // only those people. Nobody ticked: the reward is unavailable.
      item = { name: v.name, emoji: v.emoji, points: Number(v.points || 0), kind: v.kind, limit: v.limit || null, tv: v.tv, speaker: v.speaker, minutes: Number(v.minutes || 0), whole_home: !!v.whole_home, members: this._rewardMembers(v) };
    } else if (collection === "controls") {
      item = { entity_id: v.entity_id, name: v.name, emoji: v.emoji, members: v.members || [], confirm: !!v.confirm };
    } else if (collection === "members") {
      item = { name: v.name, emoji: v.emoji, color: v.color, person: v.person || null, allowance: Math.max(0, Math.round(Number(v.allowance) || 0)) };
    } else {
      item = { entity_id: v.entity_id || v.entity_id_keep, points: Number(v.points || 0), penalty: v.penalty === "" || v.penalty == null ? null : Number(v.penalty), members: v.members || [], grab: !!v.grab, due_only: !!v.due_only };
      const itemPoints = {};
      for (const input of form.querySelectorAll("[data-item-name]")) {
        const value = input.value.trim();
        if (value === "") {
          if (input.dataset.rated) itemPoints[input.dataset.itemName] = null; // back to the list's points
        } else {
          itemPoints[input.dataset.itemName] = Number(value);
        }
      }
      item.item_points = itemPoints;
      // Who each item is for; an empty list goes back to the list's people.
      const itemMembers = {};
      for (const input of form.querySelectorAll("[data-item-name]")) itemMembers[input.dataset.itemName] = [];
      for (const box of form.querySelectorAll("[data-item-member]:checked")) itemMembers[box.dataset.itemMember].push(box.value);
      item.item_members = itemMembers;
      const itemEmojis = {};
      for (const input of form.querySelectorAll("[data-item-emoji]")) itemEmojis[input.dataset.itemEmoji] = input.value.trim();
      item.item_emojis = itemEmojis;
      const itemSkip = {};
      for (const box of form.querySelectorAll("[data-item-skip]")) itemSkip[box.dataset.itemSkip] = box.checked;
      item.item_skip = itemSkip;
    }
    if (form.dataset.id) item.id = form.dataset.id;
    const ok = await this._call({ type: `${DOMAIN}/save`, collection, item }, "Saved.");
    if (ok && collection === "members") this._followMembers();
    if (ok) {
      this._edit = null;
      this._render();
    }
  }

  async _call(msg, done) {
    try {
      await this._ws(msg);
      this._toast(done);
      await this._load();
      return true;
    } catch (err) {
      this._toast(err?.message || String(err), true);
      return false;
    }
  }

  async _setGoal(rewardId) {
    const s = this._sheet;
    if (!s?.member || this._busy) return;
    const reward = this._data.rewards.find((r) => r.id === s.id);
    this._busy = true;
    try {
      await this._ws({ type: `${DOMAIN}/goal`, member_id: s.member, reward_id: rewardId });
      this._sheet = null;
      this._toast(rewardId ? `Saving for ${reward?.name || "it"}!` : "Not saving for it any more.");
      await this._load();
    } catch (err) {
      this._sheet = null;
      this._toast(err?.message || String(err), true);
    } finally {
      this._busy = false;
      this._renderOverlay();
    }
  }

  async _undo(entryId) {
    clearTimeout(this._toastTimer);
    this._toastMsg = null;
    this._renderOverlay();
    try {
      await this._ws({ type: `${DOMAIN}/undo`, entry_id: entryId });
      this._toast("Undone.");
      await this._load();
    } catch (err) {
      this._toast(err?.message || String(err), true);
    }
  }

  async _confirm() {
    const s = this._sheet;
    if (s?.type === "control") {
      const control = this._data.controls.find((c) => c.id === s.id);
      this._sheet = null;
      this._renderOverlay();
      if (control) await this._runControl(control, s.action, s.verb, s.name);
      return;
    }
    if (s?.type === "together") {
      if (this._busy || s.with.length < 2) return;
      this._busy = true;
      this._renderOverlay();
      try {
        const [first, ...rest] = s.with;
        const res = await this._ws({ type: `${DOMAIN}/redeem`, member_id: first, reward_id: s.id, together: rest });
        this._sheet = null;
        this._toast("Asked a parent! Your points are held until they say yes.", false, res.entry?.id);
        await this._load();
      } catch (err) {
        this._sheet = null;
        this._toast(err?.message || String(err), true);
      } finally {
        this._busy = false;
        this._renderOverlay();
      }
      return;
    }
    if (!s?.member || this._busy) return;
    this._busy = true;
    this._renderOverlay();
    const member = this._memberById(s.member);
    try {
      if (s.type === "chore") {
        const chore = this._data.chores.find((c) => c.id === s.id);
        const res = await this._ws({ type: `${DOMAIN}/complete`, member_id: s.member, chore_id: s.id });
        const bonus = (res.entry?.bonuses || []).map((b) => (b.points ? ` ${b.title} +${pts(b.points)}` : ` ${b.title}`)).join("");
        this._toast(`Great job, ${member.name}! +${pts(chore?.points ?? 0)}.${bonus} (${res.points} now)`, false, res.entry?.id);
        if ((res.entry?.bonuses || []).some((b) => b.bonus === "all_done")) this._celebrate(member);
      } else {
        const reward = this._data.rewards.find((r) => r.id === s.id);
        const res = await this._ws({ type: `${DOMAIN}/redeem`, member_id: s.member, reward_id: s.id });
        this._toast(`Enjoy ${reward?.name || "it"}, ${member.name}! ${pts(res.points)} left`, false, res.entry?.id);
      }
      this._sheet = null;
      await this._load();
    } catch (err) {
      this._sheet = null;
      this._toast(err?.message || String(err), true);
    } finally {
      this._busy = false;
      this._renderOverlay();
    }
  }
}

if (!customElements.get("family-panel")) customElements.define("family-panel", FamilyPanel);

// The Family dashboard as a card, for a normal dashboard: those can be a
// login's default dashboard (a shared screen's), and sidebar pages can't.
class FamilyCard extends FamilyPanel {
  constructor() {
    super();
    this._card = true;
    this._panel = { config: { mode: "family" } };
  }

  get _mode() {
    return "family";
  }

  // `member`: a family member's id, to show only their page.
  setConfig(config) {
    this._config = config || {};
    this._pinned = this._config.member || null;
    this._member = this._pinned;
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: "full", min_rows: 6 };
  }

  static getStubConfig() {
    return {};
  }
}

if (!customElements.get("family-card")) {
  customElements.define("family-card", FamilyCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "family-card",
    name: "Family",
    description: "Chores, rewards and home controls for a shared screen, for everyone or one family member.",
  });
}
