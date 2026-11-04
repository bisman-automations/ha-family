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

const REPEATS = [
  { id: "daily", label: "Every day" },
  { id: "weekly", label: "Every week" },
  { id: "once", label: "Just once" },
];

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
  input[type="text"], input[type="number"], select {
    font: inherit; font-size: 15px; padding: 8px 10px; min-height: 40px; box-sizing: border-box;
    border-radius: 8px; border: 1px solid var(--fam-divider); background: var(--fam-card); color: inherit; max-width: 100%;
  }
  .form-actions { display: flex; gap: 8px; flex-wrap: wrap; }
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
    if (this._unsub) {
      this._unsub.then((unsub) => unsub()).catch(() => {});
      this._unsub = null;
    }
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._subscribe();
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
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <div class="toolbar"><div class="menu"></div><div class="title"></div></div>
      <main></main><div class="overlay"></div>`;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("submit", (ev) => this._onSubmit(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
    this.shadowRoot.addEventListener("input", (ev) => this._onInput(ev));
  }

  _menu() {
    if (!this._built) return;
    const menu = this.shadowRoot.querySelector(".menu");
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
          <span class="points"><b>${m.points}</b> ${m.points === 1 ? "point" : "points"}</span></button>`)
      .join("")}</div>`;
  }

  _feed(entries, review = false) {
    if (!entries.length) return `<p class="empty">Nothing yet. Finished chores and spent points show up here.</p>`;
    return `<ul class="feed">${entries
      .map((e) => {
        const m = this._memberById(e.member);
        const gone = e.review === "rejected";
        const cls = gone ? "gone" : e.points >= 0 ? "plus" : "minus";
        const what = e.kind === "chore" ? `did <b>${esc(e.title)}</b>` : e.kind === "reward" ? `got <b>${esc(e.title)}</b>` : `<b>${esc(e.title)}</b>`;
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
    this.shadowRoot.querySelector(".title").textContent = this._mode === "parents" ? "Parents" : "Family";
    const main = this.shadowRoot.querySelector("main");
    if (!this._data) {
      main.innerHTML = this._error ? `<p class="error" role="alert">${esc(this._error)}</p>` : `<p class="empty">Loading…</p>`;
      return;
    }
    const error = this._error ? `<p class="error" role="alert">${esc(this._error)}</p>` : "";
    main.innerHTML = error + (this._mode === "parents" ? this._renderParents() : this._renderFamily());
    this._renderOverlay();
  }

  _renderOverlay() {
    const overlay = this.shadowRoot.querySelector(".overlay");
    if (!overlay) return;
    const t = this._toastMsg;
    const undo = t?.undo ? `<button class="undo" data-undo="${esc(t.undo)}">Undo</button>` : "";
    const toast = t ? `<div class="toast${t.bad ? " bad" : ""}" role="status"><span>${esc(t.text)}</span>${undo}</div>` : "";
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
      ? `<div class="tiles">${chores
          .map((c) => {
            const who = c.members?.length ? `<span class="who">${c.members.map((id) => this._memberById(id)).filter(Boolean).map((m) => this._avatar(m, true)).join("")}</span>` : "";
            return `<button class="tile" data-chore="${esc(c.id)}">
              ${c.emoji ? `<span class="emoji">${esc(c.emoji)}</span>` : ""}
              <span class="label">${esc(c.name)}</span>
              ${c.list ? `<span class="sub">${esc(c.list)}</span>` : ""}${who}
              <span class="worth">+${pts(c.points)}</span></button>`;
          })
          .join("")}</div>`
      : `<p class="empty">${member ? `All done, ${esc(member.name)}! No chores left right now.` : "No chores right now."}</p>`;
    const rewardTiles = d.rewards.length
      ? `<div class="tiles">${d.rewards
          .map((r) => {
            const short = member && member.points < r.points;
            const used = member && (r.used_by || []).includes(member.id);
            const sub = r.kind === "tv_time" ? `${r.minutes} min of TV${r.tv_name ? ` · ${r.tv_name}` : ""}` : "";
            const note = used ? AGAIN[r.limit] : short ? `${r.points - member.points} more to go` : LIMIT_TEXT[r.limit] || "";
            return `<button class="tile" data-reward="${esc(r.id)}" ${short || used ? "disabled" : ""}>
              ${r.emoji ? `<span class="emoji">${esc(r.emoji)}</span>` : ""}
              <span class="label">${esc(r.name)}</span>${sub ? `<span class="sub">${esc(sub)}</span>` : ""}
              <span class="worth">${pts(r.points)}</span>
              ${note ? `<span class="sub">${esc(note)}</span>` : ""}</button>`;
          })
          .join("")}</div>`
      : `<p class="empty">No rewards yet. A parent adds them on the <b>Parents</b> dashboard.</p>`;
    const feed = member ? d.recent.filter((e) => e.member === member.id) : d.recent;
    const home = this._visibleControls().length ? `<h2>Home</h2><div class="tiles home">${this._controlTiles()}</div>` : "";
    return `<h2>${member ? `Hi ${esc(member.name)}!` : "Who's here?"}</h2>
      ${this._people(d.members, "data-member", this._member)}
      <h2>Chores</h2>${choreTiles}
      <h2>Rewards</h2>${rewardTiles}
      ${home}
      <h2>Lately</h2>${this._feed(feed.slice(0, 10))}`;
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
    if (box) box.innerHTML = this._controlTiles();
    else this._seenStates = Object.fromEntries((this._data?.controls || []).map((c) => [c.entity_id, this._hass.states[c.entity_id]]));
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
    const tv = reward.kind === "tv_time" ? ` You'll get ${reward.minutes} minutes on ${esc(reward.tv_name || "the TV")} straight away.` : " A parent will give it to you.";
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
              <button class="btn bad" data-review="${esc(e.id)}" data-approved="0">Didn't happen</button></li>`;
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
        <p class="muted">Points are given as soon as a chore is marked done. <b>Didn't happen</b> takes them back${d.todo_lists.length ? " and puts a to-do item back on its list" : ""}.</p>${check}
        <label class="field"><span>Count chores nobody checked as done right</span>
          <select data-auto-check>${AUTO_CHECKS.map((a) => `<option value="${a.id}" ${auto === a.id ? "selected" : ""}>${a.label}</option>`).join("")}</select>
          <small>You can still mark one <b>Didn't happen</b> from History.</small></label></div>
      <div class="card"><h2>Rewards to hand out</h2>${give}</div>`;
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
              <small>+${pts(c.points)} · ${esc(REPEATS.find((r) => r.id === c.repeat)?.label || "")} · ${esc(this._whoText(c.members))}</small></span>
              <button class="btn" data-edit="chores" data-id="${esc(c.id)}">Edit</button>
              <button class="btn bad" data-delete="chores" data-id="${esc(c.id)}">Delete</button></li>`)
          .join("")}</ul>`
      : `<p class="empty">No chores added here yet.</p>`;
    const choreForm = edit?.collection === "chores" ? this._choreForm(edit.item) : `<button class="btn primary" data-new="chores">Add a chore</button>`;
    const lists = d.todo_lists.length
      ? `<ul class="rows">${d.todo_lists
          .map((t) => `<li><span class="grow"><b>${esc(t.name)}</b><small>+${pts(t.points)} each unless the item says otherwise · ${esc(this._whoText(t.members))}</small></span>
              <button class="btn" data-edit="todo_lists" data-id="${esc(t.id)}">Edit</button>
              <button class="btn bad" data-delete="todo_lists" data-id="${esc(t.id)}">Remove</button></li>`)
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
        <label class="field"><span>How often</span><select name="repeat">${REPEATS.map((r) => `<option value="${r.id}" ${r.id === c.repeat ? "selected" : ""}>${r.label}</option>`).join("")}</select></label>
      </div>
      <div class="field"><span>Who can do it</span>${this._whoChecks(c.members)}</div>
      <label class="check"><input type="checkbox" name="enabled" ${c.enabled ? "checked" : ""}> Show it on the Family dashboard</label>
      <div class="form-actions"><button class="btn primary" type="submit">Save chore</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  _listForm(item) {
    const t = item || { entity_id: "", points: 5, members: [] };
    const used = new Set(this._data.todo_lists.map((x) => x.entity_id));
    const options = (this._choices?.todo_lists || []).filter((l) => l.entity_id === t.entity_id || !used.has(l.entity_id));
    return `<form class="edit" data-form="todo_lists">
      <div class="inline">
        <label class="field"><span>To-do list</span><select name="entity_id" ${item ? "disabled" : ""}>${options.map((l) => `<option value="${esc(l.entity_id)}" ${l.entity_id === t.entity_id ? "selected" : ""}>${esc(l.name)}</option>`).join("") || `<option value="">No to-do lists in Home Assistant</option>`}</select></label>
        <label class="field"><span>Points for each item</span><input type="number" name="points" min="0" max="10000" value="${esc(t.points)}"></label>
      </div>
      <div class="field"><span>Who can do them</span>${this._whoChecks(t.members)}</div>
      <div class="form-actions"><button class="btn primary" type="submit">Save list</button><button class="btn" type="button" data-cancel>Cancel</button></div>
      ${item ? `<input type="hidden" name="entity_id_keep" value="${esc(t.entity_id)}">` : ""}
    </form>`;
  }

  _renderRewards() {
    const d = this._data;
    const edit = this._edit;
    const rows = d.rewards.length
      ? `<ul class="rows">${d.rewards
          .map((r) => `<li><span class="grow">${r.emoji ? `${esc(r.emoji)} ` : ""}<b>${esc(r.name)}</b>
              <small>${pts(r.points)}${r.limit ? ` · ${esc(LIMITS.find((l) => l.id === r.limit)?.label.toLowerCase() || "")}` : ""}${r.kind === "tv_time" ? ` · ${r.minutes} min on ${esc(r.tv_name || "a TV that's gone")}${r.whole_home ? " and the whole home" : ""}` : " · handed out by a parent"}</small></span>
              <button class="btn" data-edit="rewards" data-id="${esc(r.id)}">Edit</button>
              <button class="btn bad" data-delete="rewards" data-id="${esc(r.id)}">Delete</button></li>`)
          .join("")}</ul>`
      : `<p class="empty">No rewards yet.</p>`;
    const form = edit?.collection === "rewards" ? this._rewardForm(edit.item) : `<button class="btn primary" data-new="rewards">Add a reward</button>`;
    return `<div class="card"><h2>Rewards</h2>${rows}${form}</div>`;
  }

  _rewardForm(item) {
    const tvs = this._choices?.tvs || [];
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
      : `<small class="muted">A parent hands it out; it shows under To check until then.</small>`;
    return `<form class="edit" data-form="rewards" data-id="${esc(r.id || "")}">
      <div class="inline">
        <label class="field"><span>Reward</span><input type="text" name="name" value="${esc(r.name)}" required placeholder="30 minutes of TV"></label>
        <label class="field"><span>Emoji</span><input type="text" name="emoji" value="${esc(r.emoji || "")}" size="3" placeholder="📺"></label>
        <label class="field"><span>Costs</span><input type="number" name="points" min="0" max="10000" value="${esc(r.points)}"></label>
        <label class="field"><span>How often</span><select name="limit">${LIMITS.map((l) => `<option value="${l.id}" ${(r.limit || "") === l.id ? "selected" : ""}>${l.label}</option>`).join("")}</select></label>
        <label class="field"><span>What it is</span><select name="kind" data-reward-kind>
          <option value="tv_time" ${kind === "tv_time" ? "selected" : ""}>TV time</option>
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

  _renderMembers() {
    const d = this._data;
    const edit = this._edit;
    const rows = d.members.length
      ? `<ul class="rows">${d.members
          .map((m) => `<li>${this._avatar(m, true)}<span class="grow"><b>${esc(m.name)}</b> · ${pts(m.points)}
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
      ${rows}${form}</div>`;
  }

  _memberForm(item) {
    const m = item || { name: "", person: "", emoji: "", color: "" };
    // Someone already linked to another family member isn't offered again.
    const taken = new Set(this._data.members.filter((x) => x.person && x.id !== m.id).map((x) => x.person));
    const people = (this._choices?.people || []).filter((p) => !taken.has(p.entity_id));
    return `<form class="edit" data-form="members" data-id="${esc(m.id || "")}">
      <div class="inline">
        <label class="field"><span>Name</span><input type="text" name="name" value="${esc(m.name)}" required></label>
        <label class="field"><span>Emoji</span><input type="text" name="emoji" value="${esc(m.emoji || "")}" size="3" placeholder="🦖"></label>
        <label class="field"><span>Color</span><input type="color" name="color" value="${esc(m.color || "#3F51B5")}"></label>
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
      this._call({ type: `${DOMAIN}/review`, entry_id: ds.review, approved: ds.approved === "1" }, ds.approved === "1" ? "Checked." : "Points taken back.");
    } else if (ds.given) {
      this._call({ type: `${DOMAIN}/given`, entry_id: ds.given }, "Marked as handed out.");
    }
  }

  _onChange(ev) {
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
      if (key === "members") (out.members ||= []).push(value);
      else out[key] = value;
    }
    return out;
  }

  async _onSubmit(ev) {
    ev.preventDefault();
    const form = ev.target;
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
      item = { name: v.name, emoji: v.emoji, points: Number(v.points || 0), repeat: v.repeat, members: v.members || [], enabled: !!v.enabled };
    } else if (collection === "rewards") {
      item = { name: v.name, emoji: v.emoji, points: Number(v.points || 0), kind: v.kind, limit: v.limit || null, tv: v.tv, minutes: Number(v.minutes || 0), whole_home: !!v.whole_home };
    } else if (collection === "controls") {
      item = { entity_id: v.entity_id, name: v.name, emoji: v.emoji, members: v.members || [], confirm: !!v.confirm };
    } else if (collection === "members") {
      item = { name: v.name, emoji: v.emoji, color: v.color, person: v.person || null };
    } else {
      item = { entity_id: v.entity_id || v.entity_id_keep, points: Number(v.points || 0), members: v.members || [] };
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
        this._toast(`Great job, ${member.name}! +${pts(chore?.points ?? 0)} (${res.points} now)`, false, res.entry?.id);
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
