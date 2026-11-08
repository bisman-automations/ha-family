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
  h2.sec { margin: 20px 0 8px; }
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
  .form-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .items { list-style: none; margin: 4px 0 0; padding: 0; max-width: 560px; }
  .items li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--fam-divider); }
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

  _idleCheck() {
    if (this._mode !== "family" || !this._data || this._sheet || this._busy) return;
    if (Date.now() - this._lastTouch < IDLE_MS) return;
    const home = this._data.me ?? null;
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
      if (this._member === null && this._data.me && this._mode === "family") this._member = this._data.me;
      if (this._member && !this._data.members.some((m) => m.id === this._member)) this._member = null;
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

  _people(members, attr, selected) {
    return `<div class="people" role="group">${members
      .map((m) => `<button class="person" style="--c:${esc(m.color)}" ${attr}="${esc(m.id)}" aria-pressed="${m.id === selected}">
          ${this._avatar(m)}<span class="name">${esc(m.name)}</span>
          <span class="points"><b>${m.points}</b> ${m.points === 1 ? "point" : "points"}${this._data?.money ? `<small class="money"> · ${esc(money(m.points, this._data.money))}</small>` : ""}</span>
          ${m.streak >= 2 ? `<span class="streak" title="${m.streak} days in a row">🔥 ${m.streak}</span>` : ""}${this._goalBar(m)}</button>`)
      .join("")}</div>`;
  }

  // The reward someone's saving for, if it's still there.
  _goal(m) {
    return m?.goal ? this._data?.rewards.find((r) => r.id === m.goal) : null;
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

  _feed(entries, review = false) {
    if (!entries.length) return `<p class="empty">Nothing yet. Finished chores and spent points show up here.</p>`;
    return `<ul class="feed">${entries
      .map((e) => {
        const m = this._memberById(e.member);
        const gone = e.review === "rejected";
        const cls = gone ? "gone" : e.points >= 0 ? "plus" : "minus";
        const what = e.kind === "chore" ? `did <b>${esc(e.title)}</b>` : e.kind === "reward" ? `got <b>${esc(e.title)}</b>` : e.kind === "bonus" ? `earned a bonus: <b>${esc(e.title)}</b>` : e.kind === "penalty" ? `lost points: <b>${esc(e.title)}</b> didn't happen` : e.kind === "allowance" ? "got their <b>weekly allowance</b>" : `<b>${esc(e.title)}</b>`;
        const note = gone ? " · didn't happen" : e.review === "pending" ? " · to check" : e.auto ? " · checked automatically" : e.given === "to_give" ? " · to hand out" : "";
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
    const chores = d.chores.filter((c) => !member || c.can.includes(member.id));
    const choreTiles = chores.length
      ? `<div class="tiles" data-fit="chores">${chores
          .map((c) => {
            // On someone's own page, their name and picture on every tile
            // say nothing new; shared chores keep their list's name.
            const own = member && c.members?.length === 1 && c.members[0] === member.id;
            const who = !member && c.members?.length ? `<span class="who">${c.members.map((id) => this._memberById(id)).filter(Boolean).map((m) => this._avatar(m, true)).join("")}</span>` : "";
            return `<button class="tile" data-chore="${esc(c.id)}">
              ${c.emoji ? `<span class="emoji">${esc(c.emoji)}</span>` : ""}
              <span class="label">${esc(c.name)}</span>
              ${c.list && !own ? `<span class="sub">${esc(c.list)}</span>` : ""}${c.turn && !member ? `<span class="sub">${esc(this._memberById(c.turn)?.name || "Someone")}'s turn</span>` : c.turn ? `<span class="sub">Your turn</span>` : ""}${c.until_time ? `<span class="sub">Until ${esc(timeText(c.until_time))}</span>` : ""}${who}
              <span class="worth">+${pts(c.points)}</span></button>`;
          })
          .join("")}</div>`
      : `<p class="empty">${member ? `All done, ${esc(member.name)}! No chores left right now.` : "No chores right now."}</p>`;
    const rewardTiles = d.rewards.length
      ? `<div class="tiles" data-fit="rewards">${d.rewards
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
      : `<p class="empty">No rewards yet. A parent adds them on the <b>Parents</b> dashboard.</p>`;
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
    const streak = member?.streak >= 2 ? ` <span class="streak-line">🔥 ${member.streak} days in a row</span>` : "";
    const goal = this._goal(member);
    const goalCard = goal
      ? `<button class="goal-card" data-reward="${esc(goal.id)}">
          <span class="emoji">${esc(goal.emoji || "🎯")}</span>
          <span class="goal-text"><span class="label">Saving for ${esc(goal.name)}</span>
          ${this._bar(member.points, goal.points)}
          <span class="sub">${member.points >= goal.points ? "You have enough! Tap to get it." : `${member.points} of ${goal.points} · ${goal.points - member.points} more to go`}</span></span></button>`
      : "";
    const notes = (d.notes || []).filter((n) => !member || !n.member || n.member === member.id);
    // "Add a note" comes first, so it's never folded away with the rest.
    const noteTiles = `<div class="tiles notes" data-fit="notes"><button class="tile add-note" data-note-new><span class="emoji">📝</span><span class="label">Add a note</span></button>${notes.map((n) => this._noteTile(n)).join("")}</div>`;
    const events = (d.today || []).filter((e) => !member || !e.member || e.member === member.id);
    const eventTiles = `<div class="tiles events" data-fit="today">${events
      .map((e) => {
        const m = this._memberById(e.member);
        return `<div class="tile event"${m ? ` style="--c:${esc(m.color)}"` : ""}><span class="when">${esc(eventTime(e))}</span>
          <span class="label">${esc(e.title)}</span>${m && !member ? `<span class="who">${this._avatar(m, true)}</span>` : ""}</div>`;
      })
      .join("")}</div>`;
    const meals = (d.meals || []).slice(0, 2).filter((day) => MEALS.some(([k]) => day[k]));
    const mealTiles = `<div class="tiles meals" data-fit="meals">${meals
      .map((day) => {
        const index = (d.meals || []).indexOf(day);
        return `<div class="tile meal"><span class="sub">${esc(dayText(day.date, index))}</span>
          ${MEALS.filter(([k]) => day[k]).map(([k, label]) => `<span class="meal-line"><small>${label}</small> ${esc(day[k])}</span>`).join("")}</div>`;
      })
      .join("")}</div>`;
    const cash = member && d.money ? ` <span class="streak-line">${esc(money(member.points, d.money))}</span>` : "";
    return `<h2>${member ? `Hi ${esc(member.name)}!${streak}${cash}` : "Who's here?"}</h2>
      ${this._people(d.members, "data-member", this._member)}${goalCard}
      ${this._section("notes", "Notes", noteTiles, notes.length)}
      ${events.length ? this._section("today", "Today", eventTiles, events.length) : ""}
      ${meals.length ? this._section("meals", "Meals", mealTiles) : ""}
      ${this._section("chores", "Chores", choreTiles, chores.length)}
      ${done.length ? this._section("done", "Done today", doneTiles, done.length) : ""}
      ${this._section("rewards", "Rewards", rewardTiles, d.rewards.length)}
      ${home}
      ${this._section("lately", "Lately", `<div data-fit="lately">${this._feed(feed.slice(0, 10))}</div>`)}`;
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
    return this._sections[key] || "first";
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

  _section(key, title, body, count) {
    const closed = this._sectionMode(key) === "closed";
    const badge = count ? ` <span class="count">${count}</span>` : "";
    const head = `<h2 class="sec"><button class="sec-toggle" data-section-toggle="${key}" aria-expanded="${!closed}"><span class="chev"></span>${esc(title)}${badge}</button></h2>`;
    return closed ? head : `${head}${body}<button class="more" data-more="${key}" hidden></button>`;
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
    if (s.type === "control") {
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(s.verb)}">
        <h3>${esc(s.verb)} ${esc(s.name)}?</h3>
        <div class="actions"><button class="big" data-close>No</button>
        <button class="big primary" data-confirm ${this._busy ? "disabled" : ""}>Yes</button></div></div></div>`;
    }
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
      const can = d.members.filter((m) => m.points >= reward.points && !(reward.used_by || []).includes(m.id));
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Who's it for?">
        <h3>Who's ${esc(reward.name)} for?</h3><p>${pts(reward.points)}</p>
        ${can.length ? this._people(can, "data-sheet-member", null) : `<p>Nobody has enough points yet.</p>`}
        <div class="actions"><button class="big" data-close>Cancel</button></div></div></div>`;
    }
    if (member.points < reward.points) {
      const saving = member.goal === reward.id;
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Save up">
        <h3>${esc(reward.emoji || "")} ${esc(reward.name)}</h3>
        <p>${esc(member.name)} has ${member.points} of ${pts(reward.points)}: ${reward.points - member.points} more to go.${saving ? "" : " Save up for it?"}</p>
        ${this._bar(member.points, reward.points)}
        <div class="actions" style="margin-top:18px"><button class="big" data-close>Not now</button>
        ${saving ? `<button class="big" data-goal="">Stop saving for it</button>` : `<button class="big primary" data-goal="${esc(reward.id)}" ${this._busy ? "disabled" : ""}>Save for this</button>`}</div></div></div>`;
    }
    const tv = reward.kind === "tv_time" ? ` You'll get ${reward.minutes} minutes on ${esc(reward.tv_name || "the TV")} straight away.` : reward.kind === "music_time" ? ` You'll get ${reward.minutes} minutes of music on ${esc(reward.speaker_name || "the speaker")} straight away.` : " A parent will give it to you.";
    return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Get a reward">
      <h3>${esc(reward.name)}</h3><p>Spend ${pts(reward.points)} of ${esc(member.name)}'s ${member.points}?${tv}</p>
      <div class="actions"><button class="big" data-close>No</button>
      <button class="big primary" data-confirm ${this._busy ? "disabled" : ""}>Yes, please!</button></div></div></div>`;
  }

  // Parents ---------------------------------------------------------------------

  _renderParents() {
    const d = this._data;
    const checks = (d.to_check?.length || 0) + (d.to_give?.length || 0);
    const tabs = [
      ["review", `To check${checks ? `<span class="badge">${checks}</span>` : ""}`],
      ["chores", "Chores"],
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
      rewards: () => this._renderRewards(),
      home: () => this._renderHome(),
      meals: () => this._renderMeals(),
      notes: () => this._renderNotes(),
      family: () => this._renderMembers(),
      history: () => `<div class="card">${this._feed(d.history || [], true)}</div>`,
    }[this._tab]();
    return bar + body;
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
    const give = d.to_give.length
      ? `<ul class="rows">${d.to_give
          .map((e) => {
            const m = this._memberById(e.member);
            return `<li>${m ? this._avatar(m, true) : ""}<span class="grow">${esc(m?.name || "Someone")}: <b>${esc(e.title)}</b><small>${esc(whenText(e.at))}</small></span>
              <button class="btn primary" data-given="${esc(e.id)}">Handed out</button></li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No rewards to hand out.</p>`;
    const auto = d.settings?.auto_check || "";
    return `<div class="card"><h2>Chores to check</h2>
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

  _renderChores() {
    const d = this._data;
    const edit = this._edit;
    const chores = d.all_chores.length
      ? `<ul class="rows">${d.all_chores
          .map((c) => `<li><span class="grow">${c.emoji ? `${esc(c.emoji)} ` : ""}<b>${esc(c.name)}</b>${c.enabled ? "" : " (off)"}
              <small>+${pts(c.points)} · ${esc(repeatText(c))}${whenShown(c) ? ` · ${esc(whenShown(c))}` : ""} · ${esc(c.turns ? `Turns: ${this._whoText(c.members)}` : this._whoText(c.members))}${c.todo_list ? ` · on ${esc(this._listName(c.todo_list))}` : ""}</small></span>
              <button class="btn" data-edit="chores" data-id="${esc(c.id)}">Edit</button>
              <button class="btn bad" data-delete="chores" data-id="${esc(c.id)}">Delete</button></li>`)
          .join("")}</ul>`
      : `<p class="empty">No chores added here yet.</p>`;
    const choreForm = edit?.collection === "chores" ? this._choreForm(edit.item) : `<button class="btn primary" data-new="chores">Add a chore</button>`;
    const lists = d.todo_lists.length
      ? `<ul class="rows">${d.todo_lists
          .map((t) => {
            const own = (t.items || []).filter((i) => i.rated).length;
            return `<li><span class="grow"><b>${esc(t.name)}</b><small>+${pts(t.points)} each unless the item says otherwise${own ? ` · ${own} with their own points` : ""} · ${esc(this._whoText(t.members))}</small></span>
              <button class="btn" data-edit="todo_lists" data-id="${esc(t.id)}">Points for items</button>
              <button class="btn" data-edit="todo_lists" data-id="${esc(t.id)}">Edit</button>
              <button class="btn bad" data-delete="todo_lists" data-id="${esc(t.id)}">Remove</button></li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No to-do lists yet.</p>`;
    const listForm = edit?.collection === "todo_lists" ? this._listForm(edit.item) : `<button class="btn primary" data-new="todo_lists">Add a to-do list</button>`;
    return `<div class="card"><h2>Chores</h2>${chores}${choreForm}</div>
      <div class="card"><h2>Chores from to-do lists</h2>
        <p class="muted">Every open item on these lists is a chore. Put the points at the end of an item to change them, like <b>Feed the dog [5]</b>. When it's marked done, the item is ticked off its list.</p>
        ${lists}${listForm}</div>`;
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
        <small>It's added to the list while it can be done, ticked off when it's done, and opened again when it comes back.</small></label>
      <div class="field"><span>Which days</span><div class="inline">${DAYS.map((d, i) => `<label class="check"><input type="checkbox" name="days" value="${i}" ${(c.days || []).includes(i) ? "checked" : ""}> ${d}</label>`).join("")}</div>
        <small>None ticked: every day. Trash day? Tick just that day.</small></div>
      <div class="inline">
        <label class="field"><span>Shown from</span><input type="time" name="from_time" value="${esc(c.from_time || "")}"></label>
        <label class="field"><span>Until</span><input type="time" name="until_time" value="${esc(c.until_time || "")}"></label>
        <small style="align-self:end">Empty: all day. For a morning or bedtime chore, such as 6:00 AM to 9:00 AM.</small>
      </div>
      <div class="field"><span>Who can do it</span>${this._whoChecks(c.members)}</div>
      <label class="check"><input type="checkbox" name="turns" data-turns ${c.turns ? "checked" : ""}> They take turns (tick two or more people above)</label>
      <div class="inline" data-turn-fields ${c.turns ? "" : "hidden"}>
        <label class="field"><span>The turn moves on</span><select name="turn_every">${TURN_EVERY.map((t) => `<option value="${t.id}" ${(c.turn_every || "time") === t.id ? "selected" : ""}>${t.label}</option>`).join("")}</select></label>
        <label class="field"><span>Whose turn is it now?</span><select name="turn_first">${this._data.members.map((m) => `<option value="${esc(m.id)}" ${this._currentTurn(c) === m.id ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select></label>
      </div>
      <label class="check"><input type="checkbox" name="enabled" ${c.enabled ? "checked" : ""}> Show it on the Family dashboard</label>
      <div class="form-actions"><button class="btn primary" type="submit">Save chore</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
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
      ${item ? this._itemPoints(t) : ""}
      <div class="form-actions"><button class="btn primary" type="submit">Save list</button><button class="btn" type="button" data-cancel>Cancel</button></div>
      ${item ? `<input type="hidden" name="entity_id_keep" value="${esc(t.entity_id)}">` : ""}
    </form>`;
  }

  _itemPoints(list) {
    const items = list.items || [];
    const rows = items.length
      ? `<ul class="items">${items
          .map((i) => `<li><span>${esc(i.name)}</span>
            <input type="number" min="0" max="10000" aria-label="Points for ${esc(i.name)}" data-item-name="${esc(i.name)}" data-rated="${i.rated ? 1 : ""}" data-unrated="${esc(i.unrated)}" value="${i.rated ? esc(i.points) : ""}" placeholder="${esc(i.unrated)}"></li>`)
          .join("")}</ul>`
      : `<p class="muted">Nothing open on this list right now.</p>`;
    return `<div class="field"><span>Points for single items</span>
      <small>Give an item its own points. Empty: the list's points, or the points written in the item. Repeating items keep their points when they come back.</small>${rows}</div>`;
  }

  _renderRewards() {
    const d = this._data;
    const edit = this._edit;
    const rows = d.rewards.length
      ? `<ul class="rows">${d.rewards
          .map((r) => `<li><span class="grow">${r.emoji ? `${esc(r.emoji)} ` : ""}<b>${esc(r.name)}</b>
              <small>${pts(r.points)}${r.limit ? ` · ${esc(LIMITS.find((l) => l.id === r.limit)?.label.toLowerCase() || "")}` : ""}${r.kind === "tv_time" ? ` · ${r.minutes} min on ${esc(r.tv_name || "a TV that's gone")}${r.whole_home ? " and the whole home" : ""}` : r.kind === "music_time" ? ` · ${r.minutes} min of music on ${esc(r.speaker_name || "a speaker that's gone")}${r.whole_home ? " and the whole home" : ""}` : " · handed out by a parent"}</small></span>
              <button class="btn" data-edit="rewards" data-id="${esc(r.id)}">Edit</button>
              <button class="btn bad" data-delete="rewards" data-id="${esc(r.id)}">Delete</button></li>`)
          .join("")}</ul>`
      : `<p class="empty">No rewards yet.</p>`;
    const form = edit?.collection === "rewards" ? this._rewardForm(edit.item) : `<button class="btn primary" data-new="rewards">Add a reward</button>`;
    const b = d.bonus || {};
    return `<div class="card"><h2>Rewards</h2>${rows}${form}</div>
      <div class="card"><h2>Bonus points</h2>
        <form class="edit" data-bonus>
          <label class="field"><span>All of their own chores done for the day</span>
            <span><input type="number" name="bonus_all_done" min="0" max="10000" value="${esc(b.all_done || 0)}" style="width:100px"> extra points</span>
            <small>Chores anyone can do don't count, only chores picked for that person.</small></label>
          <div class="field"><span>A streak of days with a chore done</span>
            <span class="inline">Every <input type="number" name="streak_days" min="0" max="365" value="${esc(b.streak_days || 0)}" aria-label="Days in a row" style="width:80px"> days in a row:
            <input type="number" name="streak_bonus" min="0" max="10000" value="${esc(b.streak || 0)}" aria-label="Streak bonus points" style="width:100px"> extra points</span>
            <small>For example every 7 days. The Family dashboard shows each streak with 🔥.</small></div>
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
      <div class="card"><h2>Shared screen</h2>
        <p class="muted">Home Assistant only offers dashboards as a login's default, not sidebar pages like this one. Make a dashboard that shows the Family dashboard, then log in on the shared screen and pick <b>${esc(DASHBOARD_TITLE)}</b> under your profile's <b>Dashboard</b>. You can also add the <b>Family</b> card to any dashboard yourself.</p>
        <button class="btn primary" data-make-dashboard ${this._busy ? "disabled" : ""}>Make a Family dashboard</button></div>`;
  }

  async _makeDashboard() {
    if (this._busy) return;
    this._busy = true;
    try {
      const dashboards = await this._ws({ type: "lovelace/dashboards/list" });
      if (dashboards.some((d) => d.url_path === DASHBOARD_PATH)) {
        this._toast(`${DASHBOARD_TITLE} is already there.`);
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
        await this._ws({
          type: "lovelace/config/save",
          url_path: DASHBOARD_PATH,
          config: { title: DASHBOARD_TITLE, views: [{ title: "Family", path: "family", type: "panel", cards: [{ type: "custom:family-card" }] }] },
        });
        this._toast(`Made ${DASHBOARD_TITLE}. Pick it as the shared screen's default dashboard.`);
      }
    } catch (err) {
      this._toast(err?.message || String(err), true);
    } finally {
      this._busy = false;
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
      this._sheet = { type: "chore", id: ds.chore, member: this._member };
      this._renderOverlay();
    } else if (ds.reward) {
      this._sheet = { type: "reward", id: ds.reward, member: this._member };
      this._renderOverlay();
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
    } else if (ds.new) {
      this._edit = { collection: ds.new, item: null };
      this._rewardKind = null;
      this._render();
    } else if (ds.edit) {
      const list = ds.edit === "chores" ? this._data.all_chores : this._data[ds.edit];
      this._edit = { collection: ds.edit, item: list.find((x) => x.id === ds.id) };
      this._rewardKind = null;
      this._render();
    } else if ("cancel" in ds) {
      this._edit = null;
      this._render();
    } else if (ds.delete) {
      const what = { controls: "this from the Family dashboard", chores: "this chore", rewards: "this reward", members: "this family member and their points", todo_lists: "this to-do list from Family (the list itself stays)" }[ds.delete];
      if (!window.confirm(`Remove ${what}?`)) return;
      this._call({ type: `${DOMAIN}/delete`, collection: ds.delete, item_id: ds.id }, "Removed.");
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
    if (ev.target.dataset.autoCheck !== undefined) {
      this._call({ type: `${DOMAIN}/settings`, auto_check: ev.target.value || null }, "Saved.");
      return;
    }
    if (ev.target.dataset.rewardKind !== undefined) {
      // Show the TV fields for TV time, keeping what's typed so far.
      const form = ev.target.closest("form");
      const item = { ...(this._edit.item || {}), ...this._formValues(form) };
      this._rewardKind = ev.target.value;
      this._edit = { ...this._edit, item };
      this._render();
    }
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
      if (key === "members" || key === "days" || key === "notify_targets") (out[key] ||= []).push(value);
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
      item = { name: v.name, emoji: v.emoji, points: Number(v.points || 0), penalty: v.penalty === "" ? null : Number(v.penalty), repeat: v.repeat, repeat_days: Number(v.repeat_days || 1), todo_list: v.todo_list || null, members: v.members || [], enabled: !!v.enabled, days: (v.days || []).map(Number), from_time: v.from_time || null, until_time: v.until_time || null, turns: !!v.turns, turn_every: v.turn_every || "time", turn_first: v.turn_first || null };
    } else if (collection === "rewards") {
      item = { name: v.name, emoji: v.emoji, points: Number(v.points || 0), kind: v.kind, limit: v.limit || null, tv: v.tv, speaker: v.speaker, minutes: Number(v.minutes || 0), whole_home: !!v.whole_home };
    } else if (collection === "controls") {
      item = { entity_id: v.entity_id, name: v.name, emoji: v.emoji, members: v.members || [], confirm: !!v.confirm };
    } else if (collection === "members") {
      item = { name: v.name, emoji: v.emoji, color: v.color, person: v.person || null, allowance: Math.max(0, Math.round(Number(v.allowance) || 0)) };
    } else {
      item = { entity_id: v.entity_id || v.entity_id_keep, points: Number(v.points || 0), penalty: v.penalty === "" || v.penalty == null ? null : Number(v.penalty), members: v.members || [] };
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
    }
    if (form.dataset.id) item.id = form.dataset.id;
    const ok = await this._call({ type: `${DOMAIN}/save`, collection, item }, "Saved.");
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
    if (!s?.member || this._busy) return;
    this._busy = true;
    this._renderOverlay();
    const member = this._memberById(s.member);
    try {
      if (s.type === "chore") {
        const chore = this._data.chores.find((c) => c.id === s.id);
        const res = await this._ws({ type: `${DOMAIN}/complete`, member_id: s.member, chore_id: s.id });
        const bonus = (res.entry?.bonuses || []).map((b) => ` ${b.title} +${pts(b.points)}`).join("");
        this._toast(`Great job, ${member.name}! +${pts(chore?.points ?? 0)}.${bonus} (${res.points} now)`, false, res.entry?.id);
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

  setConfig(config) {
    this._config = config || {};
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
    description: "Chores, rewards and home controls for a shared screen.",
  });
}
