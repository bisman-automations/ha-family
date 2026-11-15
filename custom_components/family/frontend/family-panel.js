/*
 * Family dashboards: one plain web component, no build step.
 *
 * One page with two views:
 *   "family"  - for everyone, made for a shared touch screen: tap who you are,
 *               mark chores done, spend points on rewards, use the home
 *               controls a parent added.
 *   "parents" - the parent controls: check chores, edit chores, rewards, home
 *               controls and the family, change points, see the history.
 * The Parents button switches views: straight away for an admin, with the
 * parent PIN otherwise (family/unlock gives a pass, sent with every family/
 * command until Back to Family or the screen goes idle). panel.config.mode
 * "parents" (the old /family-parents page) starts in the parent view.
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
  const people = members.map((m) => tab(`${MEMBER_VIEW}${m.id}`, emoText(m.emoji) ? `${emoText(m.emoji)} ${m.name}` : m.name, { type: "custom:family-card", member: m.id }));
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
  { id: "fair", label: "Fairly: whoever has done it least lately" },
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
// When a hold on someone's rewards ends, in words: "Sat 6:00 PM".
const holdText = (iso) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const HOLD_FOR = [["0", "Rest of today"], ["1", "1 day"], ["2", "2 days"], ["3", "3 days"], ["7", "1 week"], ["until", "Until a day…"]];
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
// History's "Type" filter: which entry kinds each choice shows.
const HISTORY_KINDS = [
  ["", "Everything"],
  ["chore", "Chores"],
  ["reward", "Rewards and cash outs"],
  ["bonus", "Bonuses"],
  ["penalty", "Points taken away"],
  ["allowance", "Allowance"],
  ["adjust", "Changed by hand"],
  ["high_five", "High fives"],
];
const kindMatches = (kind, e) =>
  !kind ||
  (kind === "reward" ? ["reward", "cashout"].includes(e.kind)
    : kind === "bonus" ? ["bonus", "saving", "birthday"].includes(e.kind)
    : kind === "penalty" ? e.kind === "penalty" || (e.kind === "adjust" && e.points < 0)
    : e.kind === kind);
// Quick reasons a chore didn't happen.
// A picture is an emoji, or one of Home Assistant's icons ("mdi:vacuum").
const ICON_RE = /^mdi:[a-z0-9]+(-[a-z0-9]+)*$/;
const isIcon = (v) => typeof v === "string" && ICON_RE.test(v);
// The picture as HTML: the icon drawn, or the emoji escaped.
const emo = (v, fallback = "") => {
  const x = v || fallback;
  if (!x) return "";
  return isIcon(x) ? `<ha-icon class="pic" icon="${esc(x)}"></ha-icon>` : esc(x);
};
// The picture in plain text (a toast, a tab's title): icons can't be shown.
const emoText = (v) => (isIcon(v) ? "" : v || "");

// Icons for the picker: [icon, words to find it by]. Any other icon works
// too: type its name, such as mdi:washing-machine.
const PICK_ICONS = [
  ["mdi:vacuum", "vacuum hoover floor carpet"], ["mdi:robot-vacuum", "robot vacuum roomba"], ["mdi:broom", "sweep broom floor"],
  ["mdi:wiper", "wipe mop counter"], ["mdi:bucket", "bucket mop clean"], ["mdi:spray-bottle", "spray clean wipe"],
  ["mdi:spray", "spray clean"], ["mdi:liquid-spot", "spill wipe"], ["mdi:silverware-clean", "dishes clean"],
  ["mdi:dishwasher", "dishwasher dishes load unload"], ["mdi:silverware-fork-knife", "table set dinner"], ["mdi:silverware", "silverware cutlery"],
  ["mdi:pot-steam", "cook dinner pot"], ["mdi:chef-hat", "cook chef"], ["mdi:stove", "stove cook"],
  ["mdi:microwave", "microwave"], ["mdi:fridge", "fridge clean"], ["mdi:coffee-maker", "coffee"],
  ["mdi:food-apple", "fruit snack lunch"], ["mdi:food", "food meal"], ["mdi:bread-slice", "lunch sandwich"],
  ["mdi:baby-bottle", "baby bottle"], ["mdi:cup-water", "water drink"], ["mdi:glass-cocktail", "drink"],
  ["mdi:washing-machine", "laundry wash clothes"], ["mdi:tumble-dryer", "dryer laundry"], ["mdi:hanger", "hang clothes closet"],
  ["mdi:tshirt-crew", "clothes shirt fold"], ["mdi:shoe-formal", "shoes polish"], ["mdi:basket", "laundry basket"],
  ["mdi:basket-fill", "laundry basket put away"], ["mdi:iron", "iron clothes"], ["mdi:shoe-sneaker", "shoes"],
  ["mdi:bed", "bed make bedroom"], ["mdi:bed-king", "bed make"], ["mdi:bunk-bed", "bunk bed"],
  ["mdi:bed-empty", "bed sheets change"], ["mdi:sofa", "couch sofa living room tidy"], ["mdi:wardrobe", "closet wardrobe"],
  ["mdi:toy-brick", "toys lego tidy pick up"], ["mdi:teddy-bear", "toys teddy"], ["mdi:puzzle", "puzzle toys"],
  ["mdi:bookshelf", "books shelf tidy"], ["mdi:book-open-variant", "read reading book"], ["mdi:book-education", "homework study"],
  ["mdi:pencil", "homework write"], ["mdi:school", "school"], ["mdi:bag-personal", "backpack school bag"],
  ["mdi:calculator", "math homework"], ["mdi:piano", "piano practice music"], ["mdi:guitar-acoustic", "guitar practice music"],
  ["mdi:violin", "violin practice"], ["mdi:music", "music practice"], ["mdi:laptop", "computer laptop"],
  ["mdi:toothbrush", "teeth brush"], ["mdi:tooth", "teeth floss dentist"], ["mdi:shower-head", "shower"],
  ["mdi:bathtub", "bath"], ["mdi:toilet", "toilet bathroom clean"], ["mdi:hand-wash", "wash hands"],
  ["mdi:hair-dryer", "hair brush comb dry"], ["mdi:face-man-shimmer", "wash face"], ["mdi:pill", "medicine vitamins"],
  ["mdi:trash-can", "trash bin garbage"], ["mdi:delete-empty", "empty bin"], ["mdi:recycle", "recycling"],
  ["mdi:compost", "compost"], ["mdi:package-variant", "boxes package"], ["mdi:mailbox", "mail"],
  ["mdi:dog", "dog feed walk pet"], ["mdi:dog-side", "dog walk"], ["mdi:cat", "cat feed pet"],
  ["mdi:fish", "fish feed tank"], ["mdi:rabbit", "rabbit pet"], ["mdi:paw", "pet paw"],
  ["mdi:bone", "dog bone treat"], ["mdi:egg", "chickens eggs"], ["mdi:horse", "horse"],
  ["mdi:grass", "lawn grass"], ["mdi:mower", "mow lawn mower"], ["mdi:mower-bag", "mow lawn"],
  ["mdi:leaf", "leaves rake garden"], ["mdi:flower", "flowers garden"], ["mdi:watering-can", "water plants garden"],
  ["mdi:sprout", "plants garden"], ["mdi:shovel", "shovel dig snow"], ["mdi:snowflake", "snow shovel"],
  ["mdi:tree", "yard tree"], ["mdi:hammer-wrench", "fix tools"], ["mdi:tools", "tools fix"],
  ["mdi:car-wash", "car wash"], ["mdi:car", "car clean"], ["mdi:bike", "bike"],
  ["mdi:window-closed-variant", "windows clean"], ["mdi:door", "door"], ["mdi:stairs", "stairs"],
  ["mdi:home", "house home"], ["mdi:home-floor-1", "upstairs downstairs"], ["mdi:garage", "garage"],
  ["mdi:lightbulb", "lights off"], ["mdi:power-plug-off", "unplug"], ["mdi:cart", "shopping groceries"],
  ["mdi:baby-carriage", "baby"], ["mdi:human-child", "kids help sibling"], ["mdi:hand-heart", "kind help"],
  ["mdi:run", "exercise run"], ["mdi:soccer", "soccer sport"], ["mdi:basketball", "basketball sport"],
  ["mdi:swim", "swim"], ["mdi:yoga", "yoga stretch"], ["mdi:sleep", "sleep bedtime"],
  ["mdi:alarm", "wake up alarm"], ["mdi:weather-sunny", "morning"], ["mdi:weather-night", "night bedtime"],
  ["mdi:television", "tv screen time"], ["mdi:gamepad-variant", "games video"], ["mdi:tablet", "tablet ipad"],
  ["mdi:ice-cream", "ice cream treat"], ["mdi:candy", "candy treat"], ["mdi:pizza", "pizza"],
  ["mdi:popcorn", "movie popcorn"], ["mdi:movie-open", "movie"], ["mdi:cash", "money cash"],
  ["mdi:piggy-bank", "save money"], ["mdi:gift", "gift present"], ["mdi:star", "star"],
  ["mdi:trophy", "trophy win"], ["mdi:medal", "medal"], ["mdi:heart", "heart love"],
  ["mdi:party-popper", "party"], ["mdi:cake-variant", "cake birthday"], ["mdi:tent", "camp sleepover"],
  ["mdi:beach", "beach trip"], ["mdi:airplane", "trip travel"], ["mdi:map-marker", "outing place"],
];
// Chore emojis, for screens that show emojis best.
const PICK_EMOJIS = ["🧹", "🧽", "🧼", "🧺", "🪣", "🧴", "🗑️", "♻️", "🍽️", "🥣", "🍳", "🥪", "🛏️", "🧸", "📚", "✏️", "🎒", "🎹",
  "🪥", "🛁", "🚿", "🚽", "👕", "🧦", "👟", "🐶", "🐱", "🐟", "🐰", "🌱", "🌻", "🍂", "❄️", "🚗", "🛒", "📦", "🔧", "💡",
  "📺", "🎮", "🍦", "🍕", "🍿", "🎬", "💰", "🎁", "⭐", "🏆", "🎉", "❤️"];

// A photo from the camera, made small enough to send: a JPEG data URL at
// most 1024 pixels across.
async function shrinkPhoto(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    await new Promise((ok, bad) => { img.onload = ok; img.onerror = bad; img.src = url; });
    const scale = Math.min(1, 1024 / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.7);
  } finally {
    URL.revokeObjectURL(url);
  }
}

// Like model.match_points: what a parent adds to a reward someone saved for.
const matchPoints = (cost, percent) => (percent > 0 && cost > 0 ? cost - Math.ceil((cost * 100) / (100 + percent)) : 0);

// The sections a child's own phone shows.
const PHONE_SECTIONS = ["going", "mood", "chores", "bingo", "quests", "pets", "auctions", "market", "theme", "reading", "pick", "routines", "grabs", "rewards", "tomorrow"];
// The evening check-in's choices (moods.MOODS).
const MOODS = [["great", "🤩", "Great"], ["good", "🙂", "Good"], ["ok", "😐", "OK"], ["tired", "😴", "Tired"], ["sad", "😢", "Sad"], ["angry", "😠", "Angry"]];
const WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
// Minutes until it's time to leave, from the snapshot's leave (null: not now).
function leaveMinutes(leave, now = new Date()) {
  if (!leave) return null;
  const left = Math.ceil((new Date(leave.at) - now) / 60000);
  return left <= (leave.warn_minutes || 30) && left > -10 ? left : null;
}

const DIDNT_REASONS = ["Not done", "Not finished", "Not done well", "Done by someone else"];
const HIGH_FIVES = ["🙌", "⭐", "❤️", "👏", "🎉", "🤝"];
// The local day of an ISO time, as YYYY-MM-DD.
const localDayOf = (iso) => {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const dayHeading = (day) => {
  if (day === localDayIso(0)) return "Today";
  if (day === localDayIso(-1)) return "Yesterday";
  return new Date(`${day}T12:00:00`).toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
};
// Say something out loud on this screen (Read it to me).
const say = (text) => {
  try {
    const speech = window.speechSynthesis;
    if (!speech || !text) return false;
    speech.cancel();
    const words = new SpeechSynthesisUtterance(String(text));
    words.rate = 0.95;
    speech.speak(words);
    return true;
  } catch (_err) {
    return false;
  }
};
// A short beep when a chore timer runs out.
const beep = () => {
  try {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return;
    const ctx = new Audio();
    [0, 0.35, 0.7].forEach((at) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.2, ctx.currentTime + at);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + at + 0.3);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + at);
      osc.stop(ctx.currentTime + at + 0.3);
    });
  } catch (_err) {
    // No sound on this screen.
  }
};
const clockText = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.max(0, seconds) % 60).padStart(2, "0")}`;
// A CSV cell.
const csvCell = (v) => {
  const text = String(v ?? "");
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
// "MM-DD" as "Nov 20".
const monthDayText = (md) => {
  if (!md) return "";
  const [m, d] = md.split("-").map(Number);
  return `${MONTHS[m - 1]?.slice(0, 3) || ""} ${d}`;
};
// "12 days", "Tomorrow", "Today!".
const daysLeftText = (days) => (days <= 0 ? "Today!" : days === 1 ? "Tomorrow" : `${days} days`);
// A boost's end, in words: "5:00 PM" today, else "Sat 5:00 PM".
const untilText = (iso) => {
  const d = new Date(iso);
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return d.toDateString() === new Date().toDateString() ? time : `${d.toLocaleDateString([], { weekday: "short" })} ${time}`;
};
// A datetime-local input's value for a moment some hours from now.
const localInput = (hours) => {
  const d = new Date(Date.now() + hours * 3600000);
  d.setMinutes(0, 0, 0);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
// Today (0), tomorrow (1)… as an ISO date in this browser's time.
const localDayIso = (offset) => {
  const d = new Date(Date.now() + offset * 86400000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const REPORT_WEEKS = [["0", "This week"], ["1", "Last week"], ["2", "2 weeks ago"], ["3", "3 weeks ago"], ["4", "4 weeks ago"]];
// The Family dashboard's sections and their usual order (model.SECTIONS).
const SECTIONS = [
  ["going", "Going for"],
  ["mood", "How was today?"],
  ["weather", "What to wear"],
  ["countdowns", "Coming up"],
  ["vote", "What's for dinner?"],
  ["chores", "My chores"],
  ["bingo", "Chore bingo"],
  ["quests", "Quests"],
  ["pets", "Pets"],
  ["auctions", "Chore auctions"],
  ["market", "Swap market"],
  ["theme", "Theme week"],
  ["reading", "Reading"],
  ["pick", "Pick your chores"],
  ["claims", "Who did this?"],
  ["routines", "Routines"],
  ["grabs", "Up for grabs"],
  ["notes", "Notes"],
  ["today", "Today"],
  ["tomorrow", "Tomorrow"],
  ["meals", "Meals"],
  ["done", "Done today"],
  ["rewards", "Rewards"],
  ["home", "Home"],
  ["links", "Links"],
  ["screen", "Screen time left"],
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
  .meal-row { display: grid; grid-template-columns: 150px repeat(4, minmax(0, 1fr)) auto; gap: 10px; align-items: end; padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
  .meal-row .meal-day { align-self: center; }
  .meal-row .field { min-width: 0; }
  .meal-row input, .meal-row textarea { width: 100%; min-width: 0; box-sizing: border-box; }
  .card textarea { font: inherit; line-height: 1.4; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color, #fff); color: var(--primary-text-color); }
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
  .badges { display: flex; flex-wrap: wrap; gap: 6px; margin: -4px 0 12px; }
  .badge-pill { font-size: 13px; padding: 3px 10px; border-radius: 12px; background: var(--secondary-background-color, rgba(127,127,127,.12)); }
  .tile.chore { position: relative; }
  .trade-btn { position: absolute; top: 8px; right: 8px; width: 32px; height: 32px; border-radius: 50%; border: 1px solid var(--fam-divider); background: var(--card-background-color, transparent); color: inherit; font-size: 16px; cursor: pointer; }
  .trades-head { margin: 16px 0 4px; font-size: 16px; font-weight: 500; }
  .cash-preview { font-size: 20px; margin: 8px 0; min-height: 24px; }
  .weeks { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
  .week-member h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 6px; font-size: 16px; font-weight: 500; }
  .week-row { display: grid; grid-template-columns: 80px 1fr auto; gap: 8px; align-items: center; font-size: 13px; padding: 2px 0; }
  .week-bars { display: grid; gap: 2px; }
  .week-bars span { display: block; height: 6px; border-radius: 3px; min-width: 2px; }
  .bar-earned, .key-earned { background: var(--fam-good); }
  .bar-spent, .key-spent { background: var(--primary-color); }
  .key { display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: middle; }
  .week-nums { color: var(--fam-muted); white-space: nowrap; }
  .switchbar { display: flex; justify-content: flex-end; margin-bottom: 4px; }
  .switch-slot { margin-left: auto; }
  .pin-head { margin: 16px 0 2px; font-size: 16px; font-weight: 500; }
  .pin-form { align-items: flex-end; }
  .pin-form input { width: 160px; }
  .switch-slot .switchbar { margin: 0; }
  .switch-slot .btn { color: inherit; border-color: currentColor; white-space: nowrap; }
  .switchbar ha-icon { --mdc-icon-size: 18px; margin-right: 4px; }
  .sheet.pin { max-width: 340px; text-align: center; }
  .pin-dots { display: flex; justify-content: center; gap: 12px; margin: 8px 0; }
  .pin-dot { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--fam-muted); }
  .pin-dot.on { background: var(--primary-text-color); border-color: var(--primary-text-color); }
  .pin-error { color: var(--fam-bad); min-height: 20px; margin: 4px 0; }
  .pin-pad { display: grid; grid-template-columns: repeat(3, 72px); gap: 10px; justify-content: center; margin-bottom: 12px; }
  .pin-key { font: inherit; font-size: 24px; height: 60px; border-radius: 16px; border: 1px solid var(--fam-divider); background: transparent; color: inherit; cursor: pointer; }
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
  .feed .amount .balance { display: block; font-size: 12px; font-weight: 400; color: var(--secondary-text-color, #727272); white-space: nowrap; text-align: right; }
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
  .history-filter { margin-bottom: 8px; }
  .day-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 15px; margin: 18px 0 2px; padding-bottom: 4px; border-bottom: 1px solid var(--fam-divider); }
  .day-head:first-of-type { margin-top: 4px; }
  .day-totals { font-size: 13px; font-weight: 500; }
  .day-totals .plus { color: var(--fam-good); }
  .day-totals .minus { color: var(--fam-muted); }
  .more-row { text-align: center; margin-top: 12px; }
  .balance-chart { width: 100%; height: 170px; display: block; }
  .balance-chart .zero { stroke: var(--fam-divider); stroke-dasharray: 4 4; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 14px; margin-top: 6px; }
  .legend-item i { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
  .chips .chip { font: inherit; font-size: 15px; border: 1px solid var(--fam-divider); background: transparent; color: inherit; border-radius: 999px; padding: 8px 14px; cursor: pointer; min-height: 40px; }
  .chips .chip.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .five-emoji .chip { font-size: 24px; padding: 6px 12px; }
  .big.bad { border-color: var(--fam-bad); background: var(--fam-bad); color: #fff; }
  .tile-tools { position: absolute; top: 8px; right: 8px; display: flex; gap: 6px; }
  .tile-tools .trade-btn { position: static; }
  .say-btn { width: 32px; height: 32px; border-radius: 50%; border: 1px solid var(--fam-divider); background: var(--card-background-color, transparent); color: inherit; font-size: 15px; cursor: pointer; padding: 0; flex: none; }
  .steps li { display: flex; align-items: center; gap: 8px; }
  .steps li .step { flex: 1; }
  .tile.chore.pictures { cursor: pointer; }
  .tile.chore.pictures .emoji { font-size: 64px; }
  .tile.chore.pictures .label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .timer-btn { align-self: flex-start; font: inherit; font-size: 14px; border: 1px solid var(--primary-color); color: var(--primary-color); background: transparent; border-radius: 999px; padding: 6px 12px; cursor: pointer; min-height: 36px; }
  .timer-run { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--primary-color); }
  .timer-run.up { color: var(--fam-bad); }
  .timer-stop { border: 0; background: transparent; color: var(--fam-muted); font-size: 16px; cursor: pointer; padding: 2px 6px; }
  .head-extras { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: -4px 0 10px; }
  .pill-btn { font: inherit; font-size: 15px; border: 1px solid var(--fam-divider); background: var(--fam-card); color: inherit; border-radius: 999px; padding: 8px 14px; cursor: pointer; min-height: 40px; }
  .family-streak { font-size: 15px; padding: 8px 12px; border-radius: 999px; background: color-mix(in srgb, #ff9800 18%, transparent); }
  .tile.weather .sub { white-space: normal; }
  .tile.screen.out { opacity: .7; }
  .story { max-height: 60vh; overflow: auto; text-align: left; }
  .link-sheet { width: min(1100px, 96vw); max-width: none; height: min(90vh, 900px); display: flex; flex-direction: column; }
  .link-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .link-head h3 { margin: 0; }
  .link-sheet iframe { flex: 1; width: 100%; border: 1px solid var(--fam-divider); border-radius: 12px; background: #fff; margin-top: 10px; }
  .link-sheet.mobile { width: min(460px, 96vw); }
  .link-sheet.mobile iframe { width: min(390px, 100%); align-self: center; }
  .link-sheet .muted { margin: 8px 0 0; font-size: 13px; }
  .link-row { border-bottom: 1px solid var(--fam-divider); padding-bottom: 8px; margin-bottom: 8px; }
  .history-filter input[type="search"] { width: 100%; box-sizing: border-box; }
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
  details.speakers { margin: 6px 0; }
  details.speakers summary { cursor: pointer; padding: 8px 0; }
  details.speakers .speaker-find { width: 100%; max-width: 360px; margin: 6px 0; padding: 8px 10px; font: inherit; border-radius: 8px; border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color, #fff); color: inherit; }
  details.speakers label[hidden] { display: none; }
  .rows li { scroll-margin-top: 72px; }
  .rows li.edit-row { display: block; padding: 4px 0 16px; border-top: none; }
  .rows li.edit-row > form { margin: 0; padding: 16px; border-radius: 12px; background: var(--secondary-background-color, rgba(127,127,127,0.08)); }
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
  input[type="text"], input[type="password"], input[type="search"], input[type="number"], input[type="time"], select {
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
  .banner { margin: 0 0 10px; padding: 10px 14px; border-radius: 12px; font-size: 16px; }
  .banner.away { background: color-mix(in srgb, var(--info-color, #039be5) 16%, transparent); }
  .banner.boost { background: color-mix(in srgb, var(--warning-color, #f4b400) 22%, transparent); }
  .banner.birthday { background: color-mix(in srgb, #e91e63 16%, transparent); }
  .banner.leave { background: color-mix(in srgb, var(--primary-color, #03a9f4) 18%, transparent); font-size: 1.15em; font-weight: 600; }
  .banner.leave.now { background: color-mix(in srgb, var(--error-color, #db4437) 22%, transparent); }
  .photo-wall { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; max-height: 60vh; overflow: auto; }
  .photo-wall figure { margin: 0; }
  .photo-wall img, .photo-wait { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 10px; background: var(--secondary-background-color); display: grid; place-items: center; }
  .photo-wall figcaption { font-size: 13px; margin-top: 4px; }
  .tile.homework.running { outline: 2px solid var(--primary-color); }
  .quest-steps, .pet-slots { list-style: none; margin: 4px 0 0; padding: 0; display: grid; gap: 4px; font-size: 14px; }
  .quest-steps .done, .pet-slots .done { color: var(--success-color, #43a047); }
  .quest-steps .later, .pet-slots .later { opacity: .55; }
  .tile.quest, .tile.pet { align-items: stretch; }
  .freeze-btns { display: flex; gap: 6px; flex-wrap: wrap; }
  .pay { color: var(--success-color, #43a047); font-weight: 600; }
  .quiet { min-height: 80vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; text-align: center; cursor: pointer; }
  .quiet-clock { font-size: clamp(64px, 16vw, 160px); font-weight: 300; line-height: 1; }
  .quiet-day { font-size: 22px; opacity: .7; }
  .quiet-note { font-size: 20px; margin: 0; max-width: 40ch; }
  .quiet-hint { opacity: .4; margin-top: 24px; }
  .statement-nums { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 0 0 12px; }
  table.statement { width: 100%; border-collapse: collapse; }
  table.statement td { padding: 4px 6px; border-bottom: 1px solid var(--fam-divider); }
  table.statement .num { text-align: right; white-space: nowrap; }
  table.statement .neg { color: var(--error-color, #db4437); }
  .badge-count { font-weight: 600; color: #e91e63; }
  .bingo-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; max-width: 520px; }
  .bingo-cell { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; text-align: center; min-height: 92px; padding: 8px; border-radius: 14px; border: 2px dashed var(--fam-divider); font-size: 14px; }
  .bingo-cell .emoji { font-size: 26px; }
  .bingo-cell.done { border-style: solid; border-color: var(--success-color, #43a047); background: color-mix(in srgb, var(--success-color, #43a047) 14%, transparent); }
  .bingo-cell .tick { position: absolute; top: 4px; right: 8px; color: var(--success-color, #43a047); font-weight: 700; }
  .moods { display: flex; flex-wrap: wrap; gap: 8px; }
  .mood { display: flex; flex-direction: column; align-items: center; gap: 2px; min-width: 76px; padding: 10px 8px; border-radius: 14px; border: 2px solid var(--fam-divider); background: var(--card-background-color, transparent); color: inherit; font: inherit; cursor: pointer; }
  .mood .emoji { font-size: 30px; }
  .mood.on { border-color: var(--primary-color, #03a9f4); background: color-mix(in srgb, var(--primary-color, #03a9f4) 14%, transparent); }
  .moods-table li { display: flex; align-items: center; gap: 8px; }
  .mood-name { min-width: 70px; }
  .mood-days { display: flex; gap: 2px; flex-wrap: wrap; }
  .mood-day { width: 24px; text-align: center; font-size: 18px; }
  .boost-tag { color: var(--warning-color, #e09b00); font-weight: 600; }
  .tile.won { border-color: var(--success-color, #43a047); }
  .tile.countdown .worth { font-size: 20px; }
  .tile.request { position: relative; }
  .tile.request.approved { border-color: var(--success-color, #43a047); }
  .tile.request.declined { opacity: .65; }
  .tiles.requests { margin-bottom: 10px; }
  .tile.ask { border-style: dashed; }
  .tile.vote .worth { font-size: 20px; }
  .sheet.wide { max-width: 720px; width: calc(100% - 32px); max-height: 85vh; overflow: auto; }
  .report h3 { margin: 0 0 12px; }
  .report-person { border-left: 6px solid var(--c); padding: 4px 12px; margin: 0 0 14px; }
  .report-person h4 { margin: 0 0 4px; font-size: 18px; }
  .report-person p { margin: 2px 0; }
  .report-nums { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 0 0 4px; }
  .hold-note { margin: 0 0 8px; padding: 8px 12px; border-radius: 10px; background: color-mix(in srgb, var(--warning-color, #f4b400) 18%, transparent); }
  .hold-tag { font-size: 0.9em; color: var(--warning-color, #b07d00); }
  .hold-form { flex-basis: 100%; }
  .quick-edit li { flex-wrap: wrap; }
  .quick-edit .item-emoji { width: 3em; flex: none; text-align: center; font-size: 20px; padding: 4px; }
  .quick-edit .grow { flex: 1 1 160px; min-width: 0; }
  .quick-who { flex: 0 1 220px; min-width: 160px; }
  .quick-who .eligible { position: relative; }
  .quick-who .eligible-menu { position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 3; }
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
  .pic-field { display: inline-flex; }
  .chips.helpers { justify-content: center; margin-bottom: 8px; }
  p.how { text-align: left; white-space: normal; font-size: 18px; line-height: 1.5; }
  p.talk { color: var(--error-color, #db4437); }
  .wall { padding: 8px; }
  .wall-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .wall-head h1 { font-size: clamp(28px, 4vw, 56px); margin: 0 0 16px; font-weight: 500; }
  .wall-streak { font-size: clamp(18px, 2vw, 30px); }
  .wall-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
  .wall-col { background: var(--card-background-color, #fff); border-radius: 20px; padding: 18px; border-top: 8px solid var(--c, var(--primary-color)); }
  .wall-who { display: flex; align-items: center; gap: 14px; }
  .wall-who .avatar { width: 72px; height: 72px; font-size: 40px; }
  .wall-name { font-size: clamp(24px, 2.4vw, 40px); font-weight: 600; }
  .wall-points { font-size: clamp(20px, 2vw, 32px); }
  .wall-progress { display: flex; align-items: center; gap: 10px; margin: 14px 0 6px; font-size: clamp(16px, 1.6vw, 24px); }
  .wall-progress .bar { flex: 1; height: 14px; }
  .wall-list { list-style: none; padding: 0; margin: 10px 0 0; font-size: clamp(18px, 1.9vw, 30px); }
  .wall-list li { display: flex; align-items: center; gap: 10px; padding: 6px 0; }
  .wall-list li.done { opacity: 0.55; }
  .wall-list li.done .wall-done { text-decoration: line-through; }
  .wall-mark { width: 1.2em; text-align: center; color: var(--c, var(--primary-color)); font-weight: 700; }
  .wall-extra { font-size: clamp(16px, 1.6vw, 26px); margin: 16px 4px 0; }
  .photo-take { display: flex; flex-direction: column; align-items: center; gap: 8px; margin: 8px 0; }
  .photo-preview { max-width: 100%; max-height: 240px; border-radius: 12px; }
  .photo-full { max-width: 100%; max-height: 70vh; border-radius: 12px; display: block; margin: 0 auto 12px; }
  .photo-btn { cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
  .pick-turn { display: flex; align-items: center; gap: 8px; margin: 0 0 10px; }
  .tile.pick.picked { opacity: 0.75; border-color: var(--c, var(--fam-divider)); }
  .tile.pick:disabled { opacity: 0.5; }
  .rows.owed li { border-top: none; }
  .pic-btn { width: 48px; height: 48px; padding: 0; font-size: 26px; line-height: 1; display: inline-flex; align-items: center; justify-content: center; border-radius: 12px; }
  .pic-btn ha-icon, .pic-tile ha-icon { --mdc-icon-size: 28px; }
  .pic-empty { opacity: 0.45; }
  .quick-edit .pic-btn, .items .pic-btn { width: 40px; height: 40px; font-size: 20px; }
  .pic-sheet { max-height: 85vh; overflow-y: auto; text-align: left; }
  .pic-sheet h4 { margin: 14px 0 6px; }
  .pic-sheet form { margin-top: 14px; align-items: flex-end; }
  .tile .emoji ha-icon.pic, .goal-card .emoji ha-icon.pic, .pic-btn ha-icon, .pic-tile ha-icon { color: var(--primary-color, #03a9f4); }
  .pic-sheet input[type=search] { width: 100%; box-sizing: border-box; padding: 10px 12px; font: inherit; border-radius: 10px; border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color, #fff); color: inherit; }
  .pic-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(52px, 1fr)); gap: 6px; }
  .pic-tile { height: 52px; font-size: 26px; display: inline-flex; align-items: center; justify-content: center; border-radius: 12px; border: 1px solid var(--divider-color, #ddd); background: var(--card-background-color, #fff); color: var(--primary-text-color); cursor: pointer; }
  .pic-tile[hidden] { display: none; }
  .pic-own { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
  .pic-own[hidden] { display: none; }
  ha-icon.pic { --mdc-icon-size: 1em; width: 1em; height: 1em; display: inline-flex; vertical-align: -0.125em; }
  .tile .emoji ha-icon.pic, .goal-card .emoji ha-icon.pic { --mdc-icon-size: 1em; }
  .avatar ha-icon.pic { --mdc-icon-size: 60%; width: 60%; height: 60%; }
  .check-all { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 8px 0 12px; border-bottom: 1px solid var(--divider-color, #e0e0e0); margin-bottom: 4px; }
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
    this._view = null; // "family" | "parents"; null: the page's own start
    this._pass = null; // parent pass from the PIN, for logins that aren't admins
    try {
      this._sections = JSON.parse(localStorage.getItem(SECTIONS_KEY) || "{}") || {};
    } catch (_err) {
      this._sections = {};
    }
  }

  get _mode() {
    return this._view || (this._panel?.config?.mode === "parents" ? "parents" : "family");
  }

  // ---- switching between Family and the parent controls

  _openParents() {
    const d = this._data;
    if (!d) return;
    if (d.is_admin || (this._pass && d.parent)) return this._switchView("parents");
    if (!d.pin_set) {
      this._toast("Ask a parent to set a parent PIN: Parents, then the Family tab, on their own login.", true);
      return;
    }
    this._sheet = { type: "pin", pin: "", error: "" };
    this._renderOverlay();
  }

  async _unlock() {
    const s = this._sheet;
    if (!s || s.type !== "pin" || !s.pin || this._busy) return;
    this._busy = true;
    try {
      const res = await this._hass.callWS({ type: `${DOMAIN}/unlock`, pin: s.pin });
      this._pass = res.pass;
      this._passBy = res.by || null;
      this._sheet = null;
      this._busy = false;
      this._switchView("parents");
    } catch (err) {
      this._busy = false;
      s.pin = "";
      s.error = err?.message || String(err);
      this._renderOverlay();
    }
  }

  _backToFamily() {
    if (this._pass) {
      this._hass.callWS({ type: `${DOMAIN}/lock`, pass: this._pass }).catch(() => {});
      this._pass = null;
      this._passBy = null;
    }
    this._switchView("family");
  }

  _switchView(view) {
    this._view = view;
    this._sheet = null;
    this._lastTouch = Date.now();
    if (view === "family") this._member = this._homeMember();
    this._load();
  }

  _switchBar() {
    const d = this._data;
    if (!d) return "";
    if (this._mode === "parents") {
      const who = this._pass && this._passBy ? ` <span class="pass-by">(${esc(this._passBy)})</span>` : "";
      return `<div class="switchbar"><button class="btn" data-to-family><ha-icon icon="mdi:arrow-left"></ha-icon> Back to Family${who}</button></div>`;
    }
    const lock = d.is_admin ? "mdi:account-supervisor" : "mdi:lock";
    return `<div class="switchbar"><button class="btn" data-to-parents><ha-icon icon="${lock}"></ha-icon> Parents</button></div>`;
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
    if (!first && this._mode === "family" && this._data?.screen?.length) {
      // Screen time left follows TV Mgmt and Media Mgmt live.
      const seen = (this._seenScreen ||= {});
      if (this._data.screen.some((x) => hass.states[x.entity_id] !== seen[x.entity_id])) {
        for (const x of this._data.screen) seen[x.entity_id] = hass.states[x.entity_id];
        this._refreshScreen();
      }
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
    if (this._onVisible) {
      document.removeEventListener("visibilitychange", this._onVisible);
      this._onVisible = null;
    }
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
    if (this._mode === "parents" && this._pass && !this._busy && Date.now() - this._lastTouch >= IDLE_MS) {
      this._backToFamily();
      return;
    }
    if (this._mode === "family" && this._data && this._overCount() !== this._over) {
      this._over = this._overCount();
      if (this._sheet?.type === "days") this._renderOverlay();
      else if (!this._sheet && !this._busy) this._render();
    }
    if (this._mode === "family" && this._data?.quiet) {
      const quiet = this._isQuiet();
      if (quiet !== this._wasQuiet && !this._sheet && !this._busy) this._render();
      else if (quiet) {
        const clock = this.shadowRoot?.querySelector(".quiet-clock");
        if (clock) clock.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      }
    }
    if (this._mode === "family" && this._data?.leave) {
      const left = leaveMinutes(this._data.leave);
      if (left !== this._leaveLeft) {
        const was = this._leaveLeft;
        this._leaveLeft = left;
        const banner = this.shadowRoot?.querySelector("[data-leave]");
        if (banner && left != null && was != null) banner.outerHTML = this._leaveBanner();
        else if (!this._sheet && !this._busy) this._render();
      }
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
      // A load already on its way may have missed this change: once more after.
      if (this._loading) {
        this._loadAgain = true;
        return;
      }
      this._reload = setTimeout(() => this._load(), 300);
    }, { type: `${DOMAIN}/subscribe` });
  }

  async _load() {
    // Changes told before this load starts are in it: no second load for them
    // (a tap here loads straight away and the change it made is also told).
    clearTimeout(this._reload);
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      // A wall screen that's switched off doesn't need to keep up: load
      // once when it's seen again instead of after every change.
      this._stale = true;
      if (!this._onVisible) {
        this._onVisible = () => {
          if (document.visibilityState === "visible" && this._stale) this._load();
        };
        document.addEventListener("visibilitychange", this._onVisible);
      }
      return;
    }
    this._stale = false;
    if (this._loading) {
      this._loadAgain = true;
      return this._loading;
    }
    this._loading = this._loadNow();
    try {
      await this._loading;
    } finally {
      this._loading = null;
    }
    if (this._loadAgain) {
      this._loadAgain = false;
      await this._load();
    }
  }

  async _loadNow() {
    try {
      this._data = await this._ws({ type: `${DOMAIN}/state` });
      // The pass ran out (or this login isn't a parent): back to Family.
      if (this._mode === "parents" && !this._data.parent) {
        this._pass = null;
        const wanted = this._view === null;
        this._view = "family";
        if (wanted && this._data.pin_set) this._sheet = { type: "pin", pin: "", error: "" };
      }
      this._error = "";
      // Someone logged in as a family member sees their own page.
      if (this._member === null && this._mode === "family") this._member = this._homeMember();
      if (this._member && !this._data.members.some((m) => m.id === this._member)) this._member = this._homeMember();
      if (this._mode === "parents" && this._data.is_admin && this._hasDashboard === undefined) {
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
        this._choices = await this._ws({ type: `${DOMAIN}/choices` });
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
    const toolbar = this._card ? "" : `<div class="toolbar"><div class="menu"></div><div class="title"></div><div class="switch-slot"></div></div>`;
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

  // A picture field: a button showing the emoji or icon, which opens the
  // picker. The value is in a hidden input with the given attributes.
  _pic(attrs, value, placeholder = "+", label = "Picture") {
    const key = attrs.replace(/[^\w-]/g, "");
    return `<span class="pic-field" data-pic-key="${esc(key)}"><input type="hidden" ${attrs} value="${esc(value || "")}"><button type="button" class="pic-btn" data-pic-pick aria-label="${esc(label)}" title="Pick an emoji or an icon">${value ? emo(value) : `<span class="pic-empty">${esc(placeholder)}</span>`}</button></span>`;
  }

  _picField(value, placeholder) {
    return `<div class="field"><span>Picture</span>${this._pic('name="emoji"', value, placeholder)}</div>`;
  }

  _avatar(m, small = false) {
    const inner = m.picture
      ? `<img src="${esc(this._hass.hassUrl ? this._hass.hassUrl(m.picture) : m.picture)}" alt="">`
      : emo(m.emoji, m.name.slice(0, 1).toUpperCase());
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
    return `<span class="goal-mini" title="Saving for ${esc(goal.name)}">${emo(goal.emoji, "🎯")} ${this._bar(m.points, goal.points)}</span>`;
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
    if (!(this._data.members || []).length) {
      return `<small>Add family members under Family. Until then, anyone can get it.</small>`;
    }
    return this._whoDropdown(members, {
      id: "who-can-get-it",
      label: "Who can get it",
      help: "All of the family starts selected. Leave them all selected and anyone can get it, including people you add later: Family saves that as everyone. Untick people to limit it to whoever is still selected. Untick all of them and nobody can get it.",
      warn: "Nobody is selected. Nobody can get this reward until you select someone.",
    });
  }

  // The family as a dropdown of ticks. null (everyone) starts with all ticked.
  _whoDropdown(members, { id, label, help = "", warn = "", everyone = false }) {
    const people = this._data.members || [];
    const selected = members == null ? new Set(people.map((m) => m.id)) : new Set(Array.isArray(members) ? members : []);
    const chosen = people.filter((m) => selected.has(m.id));
    const shown = !chosen.length ? "Nobody" : everyone && chosen.length === people.length ? "Everyone" : chosen.map((m) => m.name).join(", ");
    const options = people
      .map((m) => {
        const on = selected.has(m.id);
        return `<label class="eligible-option" role="option" aria-selected="${on}"><input type="checkbox" name="members" value="${esc(m.id)}" data-name="${esc(m.name)}" ${on ? "checked" : ""}> ${esc(m.name)}</label>`;
      })
      .join("");
    return `<div class="eligible" data-eligible ${everyone ? "data-everyone" : ""}>
      <button type="button" class="eligible-btn" data-eligible-toggle aria-haspopup="listbox" aria-expanded="false" aria-controls="${esc(id)}" aria-label="${esc(label)}"><span data-eligible-label>${esc(shown)}</span></button>
      <div class="eligible-menu" id="${esc(id)}" data-eligible-menu role="listbox" aria-multiselectable="true" aria-label="${esc(label)}" hidden>${options}</div>
      ${help ? `<small>${esc(help)}</small>` : ""}
      ${warn ? `<small class="eligible-warn" data-eligible-warn ${chosen.length ? "hidden" : ""}>${esc(warn)}</small>` : ""}
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
    this._closeEligible(menu);
    const open = menu.hidden;
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  }

  _closeEligible(keep = null) {
    for (const menu of this.shadowRoot?.querySelectorAll("[data-eligible-menu]") || []) {
      if (menu === keep || menu.hidden) continue;
      menu.hidden = true;
      menu.parentElement.querySelector("[data-eligible-toggle]")?.setAttribute("aria-expanded", "false");
    }
  }

  // The closed label and the nobody warning follow the ticks, without
  // redrawing the form (a redraw would close the list).
  _syncEligible(root) {
    const boxes = [...root.querySelectorAll('input[name="members"]')];
    const names = boxes.filter((el) => el.checked).map((el) => el.dataset.name || "");
    const label = root.querySelector("[data-eligible-label]");
    const all = root.hasAttribute("data-everyone") && names.length === boxes.length;
    if (label) label.textContent = !names.length ? "Nobody" : all ? "Everyone" : names.join(", ");
    const warn = root.querySelector("[data-eligible-warn]");
    if (warn) warn.hidden = names.length > 0;
    for (const el of boxes) el.closest('[role="option"]')?.setAttribute("aria-selected", el.checked ? "true" : "false");
  }

  // History, narrowed to one person and/or what was done. The list redraws
  // on its own as a parent types, so the search box keeps its focus.
  // A day of the year (no year): month and day pickers named <prefix>_month
  // and <prefix>_day, filled from "MM-DD".
  _monthDay(prefix, value, label) {
    const [m, d] = (value || "").split("-");
    return `<select name="${prefix}_month" aria-label="${esc(label)}: month"><option value="">Month</option>${MONTHS.map((name, i) => {
      const v = String(i + 1).padStart(2, "0");
      return `<option value="${v}" ${v === m ? "selected" : ""}>${name}</option>`;
    }).join("")}</select>
      <select name="${prefix}_day" aria-label="${esc(label)}: day"><option value="">Day</option>${Array.from({ length: 31 }, (_v, i) => {
        const v = String(i + 1).padStart(2, "0");
        return `<option value="${v}" ${v === d ? "selected" : ""}>${i + 1}</option>`;
      }).join("")}</select>`;
  }

  _requestsCard() {
    const pending = (this._data.requests || []).filter((r) => r.status === "pending");
    if (!pending.length) return "";
    return `<div class="card"><h2>Rewards they asked for</h2>
      <p class="muted"><b>Yes</b> adds it to their rewards (just for them) at the points you set. <b>No</b> lets them know it's not this time.</p>
      <ul class="rows">${pending
        .map((r) => {
          const m = this._memberById(r.member);
          return `<li>${m ? this._avatar(m, true) : ""}<span class="grow">${esc(m?.name || "Someone")}: ${r.emoji ? `${emo(r.emoji)} ` : ""}<b>${esc(r.name)}</b><small>${esc(whenText(r.at))}${r.points != null ? ` · they think ${pts(r.points)}` : ""}</small></span>
            <input type="number" min="0" max="10000" data-request-points="${esc(r.id)}" value="${esc(r.points ?? "")}" placeholder="Points" aria-label="What ${esc(r.name)} costs" style="width:100px">
            <button class="btn good" data-request-decide="${esc(r.id)}" data-yes="1">Yes</button>
            <button class="btn bad" data-request-decide="${esc(r.id)}" data-yes="0">No</button></li>`;
        })
        .join("")}</ul></div>`;
  }

  _ideasCard() {
    const pending = (this._data.chore_ideas || []).filter((i) => i.status === "pending");
    if (!pending.length) return "";
    return `<div class="card"><h2>Chores they offered to do</h2>
      <p class="muted"><b>Yes</b> adds it as a one-off chore of theirs at the points you set. <b>No</b> lets them know it's not this time.</p>
      <ul class="rows">${pending
        .map((i) => {
          const m = this._memberById(i.member);
          return `<li>${m ? this._avatar(m, true) : ""}<span class="grow">${esc(m?.name || "Someone")}: ${i.emoji ? `${emo(i.emoji)} ` : ""}<b>${esc(i.name)}</b><small>${esc(whenText(i.at))}${i.points != null ? ` · they think ${pts(i.points)}` : ""}</small></span>
            <input type="number" min="0" max="10000" data-idea-points="${esc(i.id)}" value="${esc(i.points ?? "")}" placeholder="Points" aria-label="What ${esc(i.name)} is worth" style="width:100px">
            <button class="btn good" data-idea-decide="${esc(i.id)}" data-yes="1">Yes</button>
            <button class="btn bad" data-idea-decide="${esc(i.id)}" data-yes="0">No</button></li>`;
        })
        .join("")}</ul></div>`;
  }

  _boostCard() {
    const boosts = this._data.boosts || [];
    const name = (id) => this._data.all_chores.find((c) => c.id === id)?.name || "a chore";
    const rows = boosts.length
      ? `<ul class="rows">${boosts
          .map((b) => `<li><span class="grow">⚡ <b>${esc(b.label)}</b>: ${b.factor}× points<small>${b.on ? "On now" : `From ${esc(holdText(b.from))}`} until ${esc(holdText(b.until))} · ${b.chores?.length ? esc(namesText(b.chores.map(name))) : "every chore"}</small></span>
            <button class="btn bad" data-boost-stop="${esc(b.id)}">Stop</button></li>`)
          .join("")}</ul>`
      : "";
    const chores = this._data.all_chores.filter((c) => c.enabled);
    return `<div class="card"><h2>Double points</h2>
      <p class="muted">For a while, chores are worth two or three times their points: a Saturday cleanup, a busy week. The Family dashboard shows it at the top and on each chore.</p>
      ${rows}
      <form class="edit" data-boost-form>
        <div class="inline">
          <label class="field grow"><span>Call it (optional)</span><input type="text" name="label" maxlength="60" placeholder="Saturday cleanup"></label>
          <label class="field"><span>Points</span><select name="factor"><option value="2">Double</option><option value="3">Triple</option></select></label>
          <label class="field"><span>Until</span><input type="datetime-local" name="until" value="${esc(localInput(3))}" required></label>
        </div>
        ${chores.length ? `<div class="field"><span>Only these chores (none ticked: every chore, to-do items too)</span><div class="inline">${chores.map((c) => `<label class="check"><input type="checkbox" name="chores" value="${esc(c.id)}"> ${esc(c.name)}</label>`).join("")}</div></div>` : ""}
        <div class="form-actions"><button class="btn primary" type="submit">Start now</button></div>
      </form></div>`;
  }

  _shoppingCard() {
    const lists = this._choices?.todo_lists || [];
    const current = this._data.settings?.shopping_list || lists.find((l) => /shopping/i.test(l.entity_id))?.entity_id || "";
    const body = lists.length
      ? `<div class="inline"><label class="field"><span>Shopping list</span><select data-shopping-list>${lists.map((l) => `<option value="${esc(l.entity_id)}" ${l.entity_id === current ? "selected" : ""}>${esc(l.name)}</option>`).join("")}</select></label>
          <button class="btn primary" data-shopping style="align-self:end" ${this._busy ? "disabled" : ""}>Add to the shopping list</button></div>`
      : `<p class="empty">No to-do lists in Home Assistant yet. The Shopping List integration adds one.</p>`;
    return `<div class="card"><h2>Shopping list</h2>
      <p class="muted">Fill in <b>To buy</b> on the days above (one per line, or with commas). This puts everything today and the next days need on the list, leaving out what's already on it.</p>${body}</div>`;
  }

  async _shopping() {
    const entity = this.shadowRoot.querySelector("[data-shopping-list]")?.value;
    if (!entity || this._busy) return;
    this._busy = true;
    try {
      const res = await this._ws({ type: `${DOMAIN}/shopping`, entity_id: entity });
      const added = res.added.length ? `Added ${namesText(res.added)}.` : "Nothing new to add.";
      this._toast(res.skipped.length ? `${added} Already on it: ${namesText(res.skipped)}.` : added);
      await this._load();
    } catch (err) {
      this._toast(err?.message || String(err), true);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _voteCard() {
    const vote = this._data.vote;
    if (vote && vote.status === "open") {
      const rows = vote.options.map((name, i) => `<li><span class="grow"><b>${esc(name)}</b></span><span>${vote.counts?.[i] || 0} ${vote.counts?.[i] === 1 ? "vote" : "votes"}</span></li>`).join("");
      return `<div class="card"><h2>Dinner vote</h2>
        <p class="muted">For ${vote.day === localDayIso(0) ? "today" : esc(dayText(vote.day, -1))}${vote.closes ? `, closes at ${esc(timeText(vote.closes))}` : ""}. The winner goes on the meal plan as dinner.</p>
        <ul class="rows">${rows}</ul>
        <div class="form-actions"><button class="btn primary" data-vote-close>Close the vote now</button><button class="btn bad" data-vote-cancel>Take it down</button></div></div>`;
    }
    const done = vote && vote.winner != null ? `<p class="muted">Last vote: <b>${esc(vote.options[vote.winner])}</b> won for ${esc(dayText(vote.day, -1))}.</p>` : "";
    return `<div class="card"><h2>Dinner vote</h2>
      <p class="muted">Give two to six choices; everyone taps one on the Family dashboard. When it closes, the most votes wins (a tie: the first listed) and goes on the meal plan as dinner.</p>${done}
      <form class="edit" data-vote-form>
        <label class="field"><span>Choices, one per line</span><textarea name="options" rows="4" required placeholder="Tacos&#10;Pizza&#10;Spaghetti"></textarea></label>
        <div class="inline">
          <label class="field"><span>For</span><input type="date" name="date" value="${esc(localDayIso(0))}" min="${esc(localDayIso(0))}"></label>
          <label class="field"><span>Voting closes at (optional)</span><input type="time" name="closes" value="16:00"></label>
        </div>
        <div class="form-actions"><button class="btn primary" type="submit">Start the vote</button></div>
      </form></div>`;
  }

  _countdownCard() {
    const d = this._data;
    const rows = (d.countdowns || []).length
      ? `<ul class="rows">${d.countdowns
          .map((c) => {
            const m = this._memberById(c.member);
            return `<li><span class="grow">${emo(c.emoji, "📅")} <b>${esc(c.name)}</b><small>${esc(dayText(c.date, -1))} · ${esc(daysLeftText(c.days))}${m && !c.birthday ? ` · for ${esc(m.name)}` : ""}${c.birthday ? " · from their birthday" : ""}</small></span>
              ${c.birthday ? "" : `<button class="btn bad" data-countdown-delete="${esc(c.id)}">Remove</button>`}</li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No countdowns yet.</p>`;
    return `<div class="card"><h2>Countdowns</h2>
      <p class="muted">"12 days to the beach" on the Family dashboard. Birthdays set under Family count down by themselves, from a month before.</p>
      ${rows}
      <form class="edit" data-countdown-form>
        <div class="inline">
          <label class="field grow"><span>Counting down to</span><input type="text" name="name" maxlength="60" required placeholder="Beach trip"></label>
          ${this._picField("", "🏖️")}
          <label class="field"><span>Day</span><input type="date" name="date" min="${esc(localDayIso(0))}" required></label>
          <label class="field"><span>For</span><select name="member"><option value="">Everyone</option>${d.members.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("")}</select></label>
        </div>
        <div class="form-actions"><button class="btn primary" type="submit">Add countdown</button></div>
      </form></div>`;
  }

  _calendarAddCard() {
    const picked = this._data.settings?.calendars || [];
    if (!picked.length) return "";
    const name = (id) => this._choices?.calendars?.find((c) => c.entity_id === id)?.name || id;
    return `<div class="card"><h2>Add to the calendar</h2>
      <p class="muted">Put an event on one of the family's calendars. Leave the times empty for an all-day event.</p>
      <form class="edit" data-calendar-add>
        <div class="inline">
          <label class="field grow"><span>What</span><input type="text" name="title" maxlength="80" required placeholder="Dentist"></label>
          <label class="field"><span>Calendar</span><select name="entity_id">${picked.map((c) => `<option value="${esc(c.entity_id)}">${esc(name(c.entity_id))}</option>`).join("")}</select></label>
        </div>
        <div class="inline">
          <label class="field"><span>Day</span><input type="date" name="date" value="${esc(localDayIso(0))}" required></label>
          <label class="field"><span>From</span><input type="time" name="start"></label>
          <label class="field"><span>To</span><input type="time" name="end"></label>
          <label class="field"><span>Or all day, through</span><input type="date" name="end_date"></label>
        </div>
        <div class="form-actions"><button class="btn primary" type="submit">Add</button></div>
      </form></div>`;
  }

  _awayCard() {
    const away = this._data.away || {};
    const now = away.now
      ? `<p class="hold-note">🏖️ Away since ${esc(dayText(away.now.from, -1))}${away.now.until ? `, until ${esc(dayText(away.now.until, -1))}` : ""}.</p>
        <button class="btn primary" data-away-back>We're back home</button>`
      : "";
    const planned = (away.planned || []).length
      ? `<ul class="rows">${away.planned
          .map((p) => `<li><span class="grow">🧳 ${esc(dayText(p.from, -1))}${p.until ? ` to ${esc(dayText(p.until, -1))}` : " until you're back"}</span>
            <button class="btn bad" data-away-remove="${esc(p.id)}">Remove</button></li>`)
          .join("")}</ul>`
      : "";
    return `<div class="card"><h2>Away</h2>
      <p class="muted">While the family is away, chores and routines are off, nothing counts as missed, streaks skip those days, and the weekly allowance isn't given. Points and rewards still work.</p>
      ${now}${planned}
      ${away.now ? "" : `<form class="edit" data-away-form><div class="inline">
          <label class="field"><span>From</span><input type="date" name="from" value="${esc(localDayIso(0))}" min="${esc(localDayIso(0))}"></label>
          <label class="field"><span>Back home on (optional)</span><input type="date" name="until" min="${esc(localDayIso(0))}"></label>
        </div><small class="muted">Back home on is the last day away. Leave it empty to turn it off yourself.</small>
        <div class="form-actions"><button class="btn primary" type="submit">Set away</button></div></form>`}</div>`;
  }

  // Pick your chores: how much each one picks a week.
  _pickCard() {
    if (!this._data.picks) return "";
    const st = this._data.settings || {};
    return `<div class="card"><h2>Pick your chores</h2>
      <p class="muted">Chores ticked <b>In the pick-your-chores pool</b> are nobody's until someone picks them on the Family dashboard. Whoever has picked the fewest points this week goes next. The picks start again every Monday.</p>
      <form class="inline" data-pick-form>
        <label class="field"><span>Points each picks a week</span><input type="number" name="pick_points" min="0" max="10000" value="${esc(st.pick_points || 0)}" style="width:110px"></label>
        <small style="align-self:end">0: no limit, they pick until the pool is empty.</small>
        <button class="btn" type="submit">Save</button></form></div>`;
  }

  _savingCard() {
    const st = this._data.settings || {};
    return `<div class="card"><h2>Saving and birthday bonuses</h2>
      <form class="edit" data-saving-form>
        <div class="field"><span>Saving bonus</span>
          <span class="inline"><input type="number" name="saving_percent" min="0" max="50" value="${esc(st.saving_percent || 0)}" style="width:80px" aria-label="Percent"> % of the points kept all week, at most
          <input type="number" name="saving_max" min="0" max="10000" value="${esc(st.saving_max || 0)}" style="width:90px" aria-label="Most a week"> points <small>(0: no limit)</small></span>
          <small>Given with the allowance, on the same day and hour. "Kept" is the lower of their points now and a week ago, so spending lowers it and this week's points don't count yet. 0% turns it off.</small></div>
        <label class="field"><span>Match on saving up</span>
          <span><input type="number" name="goal_match" min="0" max="100" value="${esc(st.goal_match || 0)}" style="width:80px"> % added by a parent</span>
          <small>When someone gets the reward they're saving for, a parent adds this much of what they put in: at 25%, a 100-point reward takes 80 of their own. 0: no match.</small></label>
        <label class="field"><span>Birthday points</span>
          <span><input type="number" name="birthday_points" min="0" max="10000" value="${esc(st.birthday_points || 0)}" style="width:100px"> points on their birthday</span>
          <small>Set each person's birthday when you edit them. The Family dashboard wishes them a happy birthday either way.</small></label>
        <div class="form-actions"><button class="btn primary" type="submit">Save</button></div>
      </form></div>`;
  }

  _giveCard() {
    const st = this._data.settings || {};
    const g = st.give_goal || {};
    return `<div class="card"><h2>Give jar</h2>
      <p class="muted">Something the family gives for, such as an animal shelter or a friend's fundraiser. The kids give their own points from the Family dashboard; a share of each allowance can go in by itself.</p>
      <form class="edit" data-give-goal-form>
        <div class="inline">${this._picField(g.emoji, "💝")}
        <label class="field grow"><span>Giving for</span><input type="text" name="name" maxlength="60" value="${esc(g.name || "")}" placeholder="Animal shelter"></label>
        <label class="field"><span>Target (points)</span><input type="number" name="target" min="1" max="100000" value="${esc(g.target || "")}" style="width:110px"></label></div>
        <label class="field"><span>Share of each allowance</span><span><input type="number" name="give_percent" min="0" max="50" value="${esc(st.give_percent || 0)}" style="width:80px"> % goes in by itself <small>(0: none)</small></span></label>
        ${st.give_goal ? `<label class="check"><input type="checkbox" name="restart"> Start counting again from now</label>` : ""}
        <div class="form-actions">${st.give_goal ? `<button class="btn bad" type="button" data-give-remove>Remove</button>` : ""}<button class="btn primary" type="submit">Save</button></div>
      </form></div>`;
  }

  _themeCard() {
    const t = this._data.settings?.theme_week || {};
    return `<div class="card"><h2>Theme week</h2>
      <p class="muted">A week with a theme, such as “No screens before chores” or “Kind words”. Each day the kids tap that they kept it; you check it like a chore.</p>
      <form class="edit" data-theme-form>
        <div class="inline">${this._picField(t.emoji, "🌟")}<label class="field grow"><span>Theme</span><input type="text" name="name" maxlength="60" value="${esc(t.name || "")}" placeholder="No screens before chores"></label>
        <label class="field"><span>Points a day</span><input type="number" name="points" min="0" max="10000" value="${esc(t.points ?? 2)}" style="width:90px"></label></div>
        <div class="inline"><label class="field"><span>From</span><input type="date" name="from" value="${esc(t.from || "")}"></label><label class="field"><span>Until</span><input type="date" name="until" value="${esc(t.until || "")}"></label></div>
        <div class="form-actions">${t.name ? `<button class="btn bad" type="button" data-theme-remove>Remove</button>` : ""}<button class="btn primary" type="submit">Save</button></div>
      </form></div>`;
  }

  _extrasCard() {
    const st = this._data.settings || {};
    const r = st.reading || { block_minutes: 0, points: 0, max_minutes: 120 };
    const a = st.allowance_rule || { enabled: false, boost_at: 100, boost: 20, cut_below: 50, cut: 25 };
    return `<div class="card"><h2>Reading, homework, allowance and more</h2>
      <form class="edit" data-extras-form>
        <div class="field"><span>Reading log</span>
          <span class="inline"><input type="number" name="reading_points" min="0" max="10000" value="${esc(r.points || 0)}" style="width:80px" aria-label="Points"> points for every
          <input type="number" name="reading_block" min="0" max="240" value="${esc(r.block_minutes || 0)}" style="width:80px" aria-label="Minutes"> minutes read, up to
          <input type="number" name="reading_max" min="0" max="600" value="${esc(r.max_minutes ?? 120)}" style="width:80px" aria-label="Most minutes a day"> minutes a day</span>
          <small>The kids log their reading on the Family dashboard; it's checked under <b>To check</b> like a chore. 0 minutes: no reading log. 0 a day: no limit.</small></div>
        <div class="field"><span>Allowance rule</span>
          <label class="check"><input type="checkbox" name="rule_enabled" ${a.enabled ? "checked" : ""}> Last week's chores change this week's allowance</label>
          <span class="inline">All done on <input type="number" name="boost_at" min="0" max="100" value="${esc(a.boost_at)}" style="width:70px" aria-label="Boost from"> % of days or more: up
          <input type="number" name="boost" min="0" max="100" value="${esc(a.boost)}" style="width:70px" aria-label="Boost"> %</span>
          <span class="inline">Under <input type="number" name="cut_below" min="0" max="100" value="${esc(a.cut_below)}" style="width:70px" aria-label="Cut below"> % of days: down
          <input type="number" name="cut" min="0" max="100" value="${esc(a.cut)}" style="width:70px" aria-label="Cut"> %</span>
          <small>Counts last week's days that had their own chores; the history says why it changed.</small></div>
        <div class="field"><span>Homework timer</span>
          <span class="inline"><input type="number" name="homework_points" min="0" max="10000" value="${esc(st.homework?.points || 0)}" style="width:80px" aria-label="Points"> points for every
          <input type="number" name="homework_block" min="0" max="240" value="${esc(st.homework?.block_minutes || 0)}" style="width:80px" aria-label="Minutes"> minutes, up to
          <input type="number" name="homework_max" min="0" max="600" value="${esc(st.homework?.max_minutes ?? 120)}" style="width:80px" aria-label="Most minutes a day"> minutes a day</span>
          <small>The kids start a timer on the Family dashboard when they sit down to homework and stop it when they're done. Checked like a chore. 0 minutes: no timer.</small></div>
        <div class="field"><span>Points by age</span>
          <span class="inline">Older kids get <input type="number" name="age_percent" min="0" max="50" value="${esc(st.age_points?.percent || 0)}" style="width:70px" aria-label="Percent"> % more a year over age
          <input type="number" name="age_from" min="0" max="18" value="${esc(st.age_points?.from_age ?? 6)}" style="width:70px" aria-label="From age"></span>
          <small>Needs their birthday and year born. At 10% from 6, a 10-point chore is 12 points for an 8-year-old. 0: everyone gets the same.</small></div>
        <label class="field"><span>Rewards to buy go on</span><select name="reward_list"><option value="">No list</option>${(this._choices?.todo_lists || []).map((l) => `<option value="${esc(l.entity_id)}" ${l.entity_id === st.reward_list ? "selected" : ""}>${esc(l.name)}</option>`).join("")}</select>
          <small>When someone gets a reward a parent hands out, "A new toy for Alex" goes on this to-do list.</small></label>
        <label class="field"><span>Helping out</span><span><input type="number" name="helper_bonus" min="0" max="10000" value="${esc(st.helper_bonus || 0)}" style="width:90px"> extra points for helping a brother or sister finish a chore</span>
          <small>When a chore is marked done with helpers, each helper gets this on top of their share. 0: off.</small></label>
        <label class="field"><span>Grades and their points</span><input type="text" name="grades" value="${esc(Object.entries(st.grade_points || { A: 10, B: 6, C: 2 }).map(([g, p]) => `${g}=${p}`).join(", "))}" placeholder="A=10, B=6, C=2">
          <small>Used by the <b>Grades</b> card under To check.</small></label>
        <label class="field"><span>Beat the clock</span><span><input type="number" name="beat_clock_points" min="0" max="10000" value="${esc(st.beat_clock_points || 0)}" style="width:90px"> points for finishing a routine before it's time to leave</span>
          <small>Tick <b>Beat the clock</b> on a routine (such as Morning), and set the times under <b>Time to leave</b>. 0: off.</small></label>
        <div class="form-actions"><button class="btn primary" type="submit">Save</button></div>
      </form></div>`;
  }

  _funCard() {
    const st = this._data.settings || {};
    return `<div class="card"><h2>Bingo, races and the evening check-in</h2>
      <form class="edit" data-fun-form>
        <div class="field"><span>Chore bingo</span>
          <span class="inline"><input type="number" name="bingo_line" min="0" max="10000" value="${esc(st.bingo_line || 0)}" style="width:90px" aria-label="Points for a line"> points a line,
          <input type="number" name="bingo_full" min="0" max="10000" value="${esc(st.bingo_full || 0)}" style="width:90px" aria-label="Points for the whole card"> for the whole card</span>
          <small>Each person gets a 3×3 card of nine of their chores, new every Monday; a chore done marks its square. Needs nine chores they can do. 0 and 0: no bingo.</small></div>
        <label class="field"><span>Races</span><span><input type="number" name="challenge_points" min="0" max="10000" value="${esc(st.challenge_points || 0)}" style="width:90px"> points to whoever finishes today's own chores first</span>
          <small>A child challenges a brother or sister on the Family dashboard. 0: no races.</small></label>
        <label class="field"><span>Streak freeze</span><span><input type="number" name="freeze_cost" min="0" max="10000" value="${esc(st.freeze_cost || 0)}" style="width:90px"> points to make a missed day a day off</span>
          <small>For a sick day: yesterday, or today, once a week. 0: no freezes.</small></label>
        <div class="field"><span>Quiet hours on the shared screen</span><span class="inline"><input type="time" name="quiet_from" value="${esc(st.quiet_from || "")}" aria-label="From"> to <input type="time" name="quiet_until" value="${esc(st.quiet_until || "")}" aria-label="Until"></span>
          <small>After a while with no taps, the Family dashboard rests: a big clock, time to leave and notes, until someone taps it. Leave both empty for never.</small></div>
        <label class="check"><input type="checkbox" name="mood_check" ${st.mood_check ? "checked" : ""}> Evening check-in: each person taps how their day was. Only parents see it, under <b>History</b>.</label>
        <div class="form-actions"><button class="btn primary" type="submit">Save</button></div>
      </form></div>`;
  }

  _leaveCard() {
    const st = this._data.settings || {};
    const times = st.leave_times || {};
    return `<div class="card"><h2>Time to leave</h2>
      <p class="muted">A countdown across the top of the Family dashboard (and the wall view) on mornings you leave, such as for school. Leave a day empty for none.</p>
      <form class="edit" data-leave-form>
        <div class="inline">${WEEKDAY_NAMES.map((name, i) => `<label class="field"><span>${name}</span><input type="time" name="day${i}" value="${esc(times[String(i)] || "")}"></label>`).join("")}</div>
        <label class="field"><span>Show it</span><span><input type="number" name="leave_warn" min="1" max="120" value="${esc(st.leave_warn || 30)}" style="width:80px"> minutes before</span></label>
        <div class="form-actions"><button class="btn primary" type="submit">Save</button></div>
      </form></div>`;
  }

  _payoutsCard() {
    if (!this._data.money) return "";
    const cur = this._data.money?.currency || "";
    const months = this._payouts;
    const table = months ? `<div class="table-wrap"><table class="payouts"><thead><tr><th>Month</th>${this._data.members.map((m) => `<th>${esc(m.name)}</th>`).join("")}</tr></thead><tbody>${months.map((row) => `<tr><td>${esc(new Date(`${row.month}-15`).toLocaleDateString([], { month: "long", year: "numeric" }))}</td>${this._data.members.map((m) => {
      const p = row.people.find((x) => x.member === m.id) || { asked: 0, paid: 0 };
      return `<td>${p.asked ? `${esc(cur)}${p.paid.toFixed(2)}${p.paid < p.asked ? ` <small>of ${esc(cur)}${p.asked.toFixed(2)}</small>` : ""}` : "—"}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>` : "";
    return `<div class="card"><h2>Money paid out</h2>
      <p class="muted">Each month, how much each child cashed out and how much of it was paid.</p>
      ${table}<div class="form-actions"><button class="btn${months ? "" : " primary"}" data-payouts-load>${months ? "Refresh" : "Show the last six months"}</button>${months ? `<button class="btn" data-payouts-csv>⬇︎ Spreadsheet</button>` : ""}</div></div>`;
  }

  _payoutsCsv() {
    const months = this._payouts || [];
    const head = ["Month", ...this._data.members.flatMap((m) => [`${m.name} cashed out`, `${m.name} paid`])];
    const lines = [head, ...months.map((row) => [row.month, ...this._data.members.flatMap((m) => {
      const p = row.people.find((x) => x.member === m.id) || { asked: 0, paid: 0 };
      return [p.asked.toFixed(2), p.paid.toFixed(2)];
    })])].map((cells) => cells.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","));
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    link.download = "family-payouts.csv";
    link.click();
  }

  _photosCard() {
    return `<div class="card"><h2>Photos of the month</h2>
      <p class="muted">Every chore photo from a month on one page, to look back on or print for the fridge.</p>
      <div class="form-actions"><button class="btn primary" data-photos-month="0">This month</button><button class="btn" data-photos-month="1">Last month</button></div></div>`;
  }

  async _openPhotos(monthsAgo) {
    this._sheet = { type: "photos", photos: null, urls: {} };
    this._renderOverlay();
    try {
      const { photos } = await this._ws({ type: `${DOMAIN}/photos/month`, months_ago: monthsAgo });
      if (this._sheet?.type !== "photos") return;
      this._sheet.photos = photos;
      this._renderOverlay();
      for (const p of photos) {
        const res = await this._ws({ type: `${DOMAIN}/photo`, entry_id: p.entry_id }).catch(() => null);
        if (this._sheet?.type !== "photos") return;
        if (res?.url) this._sheet.urls[p.entry_id] = res.url;
        this._renderOverlay();
      }
    } catch (err) {
      this._sheet = null;
      this._renderOverlay();
      this._toast(err?.message || String(err), true);
    }
  }

  _printPhotos() {
    const s = this._sheet;
    if (!s?.photos) return;
    const win = window.open("", "_blank");
    if (!win) return;
    const cells = s.photos.filter((p) => s.urls[p.entry_id]).map((p) => `<figure><img src="${esc(s.urls[p.entry_id])}" alt=""><figcaption>${esc(p.title)} · ${esc(this._memberById(p.member)?.name || "")} · ${esc(new Date(p.at).toLocaleDateString())}</figcaption></figure>`).join("");
    win.document.write(`<!doctype html><title>Photos of the month</title><style>body{font-family:sans-serif;margin:16px}div{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}img{width:100%;border-radius:8px}figure{margin:0}figcaption{font-size:12px;color:#555}</style><h1>Photos of the month</h1><div>${cells}</div>`);
    win.document.close();
    win.focus();
    win.print();
  }

  _statementCard() {
    const months = Array.from({ length: 6 }, (_v, i) => {
      const d = new Date();
      d.setDate(1);
      d.setMonth(d.getMonth() - i);
      return [String(i), d.toLocaleDateString([], { month: "long", year: "numeric" })];
    });
    return `<div class="card"><h2>Pocket money statement</h2>
      <p class="muted">One person's month, like a bank statement: points at the start, everything earned, spent, given and taken away, and points at the end. Print it for them.</p>
      <form class="inline" data-statement-form>
        <label class="field"><span>Who</span><select name="member_id">${this._data.members.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("")}</select></label>
        <label class="field"><span>Month</span><select name="months_ago">${months.map(([v, label]) => `<option value="${v}">${esc(label)}</option>`).join("")}</select></label>
        <button class="btn primary" type="submit" style="align-self:end">Show it</button></form></div>`;
  }

  _statementBody(st) {
    const cash = (n) => (st.money ? ` <small>(${esc(money(n, st.money))})</small>` : "");
    const month = new Date(`${st.start}T12:00:00`).toLocaleDateString([], { month: "long", year: "numeric" });
    return `<h3>${esc(st.member)}: ${esc(month)}</h3>
      <div class="statement-nums"><span>Start <b>${st.opening}</b>${cash(st.opening)}</span><span>Earned <b>+${st.earned}</b></span><span>Spent <b>−${st.spent}</b></span>${st.given ? `<span>Given <b>−${st.given}</b></span>` : ""}${st.taken ? `<span>Taken away <b>−${st.taken}</b></span>` : ""}<span>End <b>${st.closing}</b>${cash(st.closing)}</span></div>
      <table class="statement"><tbody>${st.lines.map((l) => `<tr><td>${esc(new Date(l.at).toLocaleDateString([], { month: "short", day: "numeric" }))}</td><td>${esc(l.title)}</td><td class="num ${l.points < 0 ? "neg" : ""}">${l.points > 0 ? "+" : ""}${l.points}</td></tr>`).join("") || `<tr><td colspan="3" class="muted">Nothing this month.</td></tr>`}</tbody></table>`;
  }

  _printStatement() {
    const st = this._sheet?.statement;
    if (!st) return;
    const w = window.open("", "_blank");
    if (!w) {
      this._toast("Allow pop-ups for Home Assistant to print it.", true);
      return;
    }
    w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(st.member)}</title>
      <style>body{font-family:system-ui,sans-serif;margin:24px;color:#222}.statement-nums{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 12px}table{border-collapse:collapse;width:100%}td{border-bottom:1px solid #ddd;padding:4px 6px}.num{text-align:right}.neg{color:#b00}.muted{color:#666}</style></head>
      <body>${this._statementBody(st)}</body></html>`);
    w.document.close();
    w.focus();
    w.print();
  }

  _questsCard() {
    const quests = this._data.quests || [];
    const editing = this._questEdit;
    const rows = quests.map((q) => `<li><span class="grow">${emo(q.emoji, "🗺️")} <b>${esc(q.name)}</b><small>${q.done.length} of ${q.steps.length} steps done${q.members ? ` · ${esc(namesText(q.members.map((id) => this._memberById(id)?.name).filter(Boolean)))}` : ""}</small></span>
        ${q.done.length ? `<button class="btn" data-quest-undo="${esc(q.id)}">Put back the last step</button>` : ""}
        <button class="btn" data-quest-edit="${esc(q.id)}">Edit</button><button class="btn bad" data-quest-delete="${esc(q.id)}">Remove</button></li>`).join("");
    const q = editing === "new" ? {} : quests.find((x) => x.id === editing);
    const form = q ? `<form class="edit" data-quest-form>
        <input type="hidden" name="id" value="${esc(q.id || "")}">
        <div class="inline">${this._picField(q.emoji, "🗺️")}<label class="field grow"><span>Quest</span><input type="text" name="name" maxlength="60" required value="${esc(q.name || "")}" placeholder="Clear out the garage"></label></div>
        <label class="field"><span>Steps, in order: one on each line, with points at the end</span><textarea name="steps" rows="5" placeholder="Sort the toys [5]&#10;Sweep the floor [3]&#10;Take the boxes out [5]">${esc((q.steps || []).map((st) => `${st.name}${st.points ? ` [${st.points}]` : ""}`).join("\n"))}</textarea></label>
        <div class="field"><span>Who can do it</span>${this._whoDropdown(q.members ?? null, { id: "quest-who", label: "Who can do it", everyone: true })}</div>
        <div class="form-actions"><button class="btn" type="button" data-quest-edit="">Cancel</button><button class="btn primary" type="submit">Save</button></div></form>`
      : `<button class="btn primary" data-quest-edit="new">Add a quest</button>`;
    return `<div class="card"><h2>Quests</h2>
      <p class="muted">A bigger job in steps, such as clearing out the garage. The steps open one at a time on the Family dashboard; whoever does one gets its points.</p>
      ${rows ? `<ul class="rows">${rows}</ul>` : ""}${form}</div>`;
  }

  _petsCard() {
    const pets = this._data.pets || [];
    const editing = this._petEdit;
    const rows = pets.map((p) => `<li><span class="grow">${emo(p.emoji, "🐾")} <b>${esc(p.name)}</b><small>${esc(p.task)} at ${esc(p.times.map(timeText).join(", "))}${p.points ? ` · +${pts(p.points)} each` : ""}</small></span>
        <button class="btn" data-pet-edit="${esc(p.id)}">Edit</button><button class="btn bad" data-pet-delete="${esc(p.id)}">Remove</button></li>`).join("");
    const p = editing === "new" ? { task: "Feed" } : pets.find((x) => x.id === editing);
    const form = p ? `<form class="edit" data-pet-form>
        <input type="hidden" name="id" value="${esc(p.id || "")}">
        <div class="inline">${this._picField(p.emoji, "🐶")}<label class="field grow"><span>Name</span><input type="text" name="name" maxlength="60" required value="${esc(p.name || "")}" placeholder="Rex"></label>
        <label class="field"><span>What</span><input type="text" name="task" maxlength="30" value="${esc(p.task || "Feed")}" style="width:120px"></label></div>
        <div class="inline"><label class="field grow"><span>Times (separated by commas)</span><input type="text" name="times" value="${esc((p.times || []).join(", "))}" placeholder="07:00, 18:00"></label>
        <label class="field"><span>Points each time</span><input type="number" name="points" min="0" max="10000" value="${esc(p.points || 0)}" style="width:100px"></label></div>
        <div class="form-actions"><button class="btn" type="button" data-pet-edit="">Cancel</button><button class="btn primary" type="submit">Save</button></div></form>`
      : `<button class="btn primary" data-pet-edit="new">Add a pet</button>`;
    return `<div class="card"><h2>Pets</h2>
      <p class="muted">Each pet's meals (or walks) at set times. Each one can be done once, from an hour before its time, so nobody feeds the dog two breakfasts. It's checked under <b>To check</b> like a chore.</p>
      ${rows ? `<ul class="rows">${rows}</ul>` : ""}${form}</div>`;
  }

  _mostWantedCard() {
    const wanted = this._data.most_wanted || [];
    if (!wanted.length) return "";
    const rows = wanted.map((w) => {
      const r = this._data.rewards.find((x) => x.id === w.reward_id);
      if (!r) return "";
      return `<li><span class="grow">${emo(r.emoji, "🎁")} <b>${esc(r.name)}</b><small>${pts(r.points)} · wished for by ${esc(namesText(w.members.map((id) => this._memberById(id)?.name).filter(Boolean)))}</small></span><span class="badge-count">♥ ${w.members.length}</span></li>`;
    }).join("");
    return `<div class="card"><h2>Most wanted</h2><p class="muted">The rewards on the kids' wishlists (up to three each), the most wished for first.</p><ul class="rows">${rows}</ul></div>`;
  }

  _moodsCard() {
    const moods = this._data.moods;
    if (!moods) return "";
    const face = Object.fromEntries(MOODS.map(([id, emoji, label]) => [id, [emoji, label]]));
    const rows = this._data.members.map((m) => {
      const days = moods[m.id] || [];
      return `<li>${this._avatar(m, true)}<span class="mood-name">${esc(m.name)}</span><span class="mood-days">${days.map((x) => `<span class="mood-day" title="${esc(dayText(x.date, -1))}${x.mood ? `: ${esc(face[x.mood]?.[1] || x.mood)}` : ""}">${x.mood ? face[x.mood]?.[0] || "?" : "·"}</span>`).join("")}</span></li>`;
    }).join("");
    return `<div class="card"><h2>How their days were</h2>
      <p class="muted">The evening check-in, the last two weeks (oldest first). Worth a chat when one keeps coming up sad or angry.</p>
      <ul class="rows moods-table">${rows}</ul></div>`;
  }

  _reportCard() {
    return `<div class="card"><h2>Weekly report</h2>
      <p class="muted">A week for everyone, Monday to Sunday: chores done, points earned and spent, rewards and badges. Print it for the fridge or share it.</p>
      <form class="inline" data-report-form>
        <label class="field"><span>Week</span><select name="weeks_ago">${REPORT_WEEKS.map(([v, label]) => `<option value="${v}">${label}</option>`).join("")}</select></label>
        <button class="btn primary" type="submit" style="align-self:end">Show the report</button>
        <button class="btn" type="button" data-meeting style="align-self:end">Family meeting</button></form>
      <p class="muted"><b>Family meeting</b> is this week's report for sitting down together on Sunday: what went well, chores that didn't happen (and why) to talk about, and what's on for next week.</p></div>`;
  }

  async _openReport(weeksAgo, meeting = false) {
    this._sheet = { type: "report", report: null, meeting };
    this._renderOverlay();
    try {
      const res = await this._ws({ type: `${DOMAIN}/report`, weeks_ago: weeksAgo });
      if (this._sheet?.type === "report") this._sheet.report = res.report;
    } catch (err) {
      this._sheet = null;
      this._toast(err?.message || String(err), true);
    }
    this._renderOverlay();
  }

  _reportTitle(r) {
    const fmt = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
    return `${this._sheet?.meeting ? "Family meeting" : "Family week"}: ${fmt(r.from)} to ${fmt(r.until)}`;
  }

  _reportBody(r) {
    const people = r.members
      .map((m) => {
        const chores = m.top_chores.map((c) => `${esc(c.name)}${c.times > 1 ? ` ×${c.times}` : ""}`).join(", ");
        const cash = r.money ? ` (${esc(money(m.points, r.money))})` : "";
        return `<section class="report-person" style="--c:${esc(m.color || "#3F51B5")}">
          <h4>${emo(m.emoji, "")} ${esc(m.name)}</h4>
          <div class="report-nums"><span><b>${m.chores}</b> chores</span><span><b>+${m.earned}</b> earned</span><span><b>${m.spent}</b> spent</span><span><b>${m.points}</b> now${cash}</span><span>🔥 <b>${m.streak}</b> in a row</span></div>
          ${chores ? `<p>Chores: ${chores}</p>` : ""}
          ${m.all_done_days ? `<p>All done on ${m.all_done_days} ${m.all_done_days === 1 ? "day" : "days"}.</p>` : ""}
          ${m.rewards.length ? `<p>Got: ${m.rewards.map(esc).join(", ")}</p>` : ""}
          ${m.badges.length ? `<p>New badges: ${m.badges.map((b) => `${esc(b.emoji)} ${esc(b.name)}`).join(", ")}</p>` : ""}
          ${(m.didnt || []).length ? `<p class="talk">To talk about: ${m.didnt.map((x) => `${esc(x.title)}${x.reason ? ` (${esc(x.reason)})` : ""}`).join(", ")}</p>` : ""}
          ${(m.next_week || []).length && this._sheet?.meeting ? `<p>Next week: ${m.next_week.map(esc).join(", ")}</p>` : ""}
        </section>`;
      })
      .join("");
    return `<div class="report"><h3>${esc(this._reportTitle(r))}</h3>${r.days_away ? `<p class="muted">Away ${r.days_away} ${r.days_away === 1 ? "day" : "days"} this week.</p>` : ""}${people || `<p class="empty">No family members yet.</p>`}</div>`;
  }

  _reportText(r) {
    const lines = [this._reportTitle(r)];
    for (const m of r.members) {
      lines.push("", `${m.name}: ${m.chores} chores, +${m.earned} earned, ${m.spent} spent, ${m.points} now, ${m.streak} days in a row`);
      if (m.top_chores.length) lines.push(`Chores: ${m.top_chores.map((c) => `${c.name}${c.times > 1 ? ` ×${c.times}` : ""}`).join(", ")}`);
      if (m.rewards.length) lines.push(`Got: ${m.rewards.join(", ")}`);
      if (m.badges.length) lines.push(`New badges: ${m.badges.map((b) => `${b.emoji} ${b.name}`).join(", ")}`);
      if ((m.didnt || []).length) lines.push(`To talk about: ${m.didnt.map((x) => `${x.title}${x.reason ? ` (${x.reason})` : ""}`).join(", ")}`);
    }
    return lines.join("\n");
  }

  // Printed from a window of its own, so only the report is on the page.
  _printReport() {
    const r = this._sheet?.report;
    if (!r) return;
    const w = window.open("", "_blank");
    if (!w) {
      this._toast("Allow pop-ups for Home Assistant to print the report.", true);
      return;
    }
    w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(this._reportTitle(r))}</title>
      <style>body{font-family:system-ui,sans-serif;margin:24px;color:#222}h3{margin:0 0 12px}.report-person{border-left:6px solid var(--c);padding:4px 12px;margin:0 0 14px;break-inside:avoid}
      h4{margin:0 0 4px;font-size:18px}.report-nums{display:flex;flex-wrap:wrap;gap:4px 16px;margin:0 0 4px}p{margin:2px 0}.muted{color:#666}</style></head>
      <body>${this._reportBody(r)}</body></html>`);
    w.document.close();
    w.focus();
    w.print();
  }

  async _shareReport() {
    const r = this._sheet?.report;
    if (!r) return;
    const text = this._reportText(r);
    try {
      if (navigator.share) {
        await navigator.share({ title: this._reportTitle(r), text });
        return;
      }
      await navigator.clipboard.writeText(text);
      this._toast("Copied. Paste it into a message.");
    } catch (err) {
      if (err?.name !== "AbortError") this._toast("Couldn't share it from here. Try Print instead.", true);
    }
  }

  _renderHistory() {
    const f = (this._historyFilter ||= { member: "", text: "", kind: "" });
    const people = this._data.members.map((m) => `<option value="${esc(m.id)}" ${f.member === m.id ? "selected" : ""}>${esc(m.name)}</option>`).join("");
    const kinds = HISTORY_KINDS.map(([k, label]) => `<option value="${k}" ${f.kind === k ? "selected" : ""}>${esc(label)}</option>`).join("");
    return `${this._reportCard()}${this._statementCard()}${this._payoutsCard()}${this._photosCard()}${this._moodsCard()}${this._balanceChart()}${this._weeksCard()}<div class="card"><div class="history-filter inline">
        <label class="field"><span>Who</span><select data-history-member aria-label="Who"><option value="">Everyone</option>${people}</select></label>
        <label class="field"><span>Type</span><select data-history-kind aria-label="Type">${kinds}</select></label>
        <label class="field grow"><span>Search</span><input type="search" data-history-text value="${esc(f.text)}" placeholder="A chore, reward or bonus" aria-label="Search history"></label>
        <button class="btn" data-history-csv style="align-self:end" title="Download what's shown as a spreadsheet">⬇︎ Spreadsheet</button>
      </div><div data-history-list>${this._historyList()}</div></div>`;
  }

  // Everything loaded so far: the newest from the snapshot, then older pages.
  _historyAll() {
    const seen = new Set();
    return [...(this._data.history || []), ...(this._olderHistory || [])].filter((e) => !seen.has(e.id) && seen.add(e.id));
  }

  _historyMatches(all) {
    const f = this._historyFilter || { member: "", text: "", kind: "" };
    const words = f.text.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return all.filter((e) => (!f.member || e.member === f.member) && kindMatches(f.kind, e) && words.every((w) => (e.title || "").toLowerCase().includes(w)));
  }

  // Each person's points at the end of each of the last four weeks.
  _balanceChart() {
    const data = this._data.balance_days;
    const members = this._data.members;
    if (!data?.days?.length || !members.length) return "";
    const values = members.flatMap((m) => data.members[m.id] || []);
    if (!values.length) return "";
    const low = Math.min(0, ...values);
    const high = Math.max(1, ...values);
    const W = 600;
    const H = 170;
    const pad = 6;
    const x = (i) => pad + (i * (W - pad * 2)) / Math.max(1, data.days.length - 1);
    const y = (v) => H - pad - ((v - low) * (H - pad * 2)) / (high - low || 1);
    const lines = members
      .map((m) => {
        const series = data.members[m.id] || [];
        if (!series.length) return "";
        const d = series.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
        return `<polyline points="${d}" fill="none" stroke="${esc(m.color || "#3F51B5")}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"><title>${esc(m.name)}</title></polyline>`;
      })
      .join("");
    const zero = low < 0 ? `<line x1="${pad}" x2="${W - pad}" y1="${y(0)}" y2="${y(0)}" class="zero" vector-effect="non-scaling-stroke"></line>` : "";
    const first = new Date(`${data.days[0]}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
    const legend = members
      .map((m) => {
        const series = data.members[m.id] || [];
        return `<span class="legend-item"><i style="background:${esc(m.color || "#3F51B5")}"></i>${esc(m.name)} <b>${series.at(-1) ?? 0}</b></span>`;
      })
      .join("");
    return `<div class="card"><h2>Points over time</h2>
      <p class="muted">Each person's points at the end of each day, from ${esc(first)} to today.</p>
      <svg class="balance-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Points over the last ${data.days.length} days">${zero}${lines}</svg>
      <div class="legend">${legend}</div></div>`;
  }

  // Points earned and spent, and chores done, per person over the last weeks.
  _weeksCard() {
    const weeks = this._data.weeks || [];
    const members = this._data.members;
    if (!weeks.length || !members.length) return "";
    const max = Math.max(1, ...weeks.flatMap((w) => Object.values(w.members).flatMap((v) => [v.earned, v.spent])));
    const label = (iso, i) => (i === weeks.length - 1 ? "This week" : new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }));
    const blocks = members.map((m) => {
      const rows = weeks.map((w, i) => {
        const v = w.members[m.id] || { earned: 0, spent: 0, chores: 0 };
        return `<div class="week-row"><span class="week-label">${esc(label(w.week, i))}</span>
          <span class="week-bars"><span class="bar-earned" style="width:${(v.earned / max) * 100}%"></span><span class="bar-spent" style="width:${(v.spent / max) * 100}%"></span></span>
          <span class="week-nums">+${v.earned} · −${v.spent} · ${v.chores} chore${v.chores === 1 ? "" : "s"}</span></div>`;
      });
      return `<div class="week-member"><h3>${this._avatar(m, true)} ${esc(m.name)}</h3>${rows.join("")}</div>`;
    });
    return `<div class="card"><h2>Week by week</h2>
      <p class="muted">Points earned <span class="key key-earned"></span> and spent <span class="key key-spent"></span> each week (Monday to Sunday), and chores done. Chores that didn't happen don't count.</p>
      <div class="weeks">${blocks.join("")}</div></div>`;
  }

  _historyList() {
    const f = this._historyFilter || { member: "", text: "", kind: "" };
    const all = this._historyAll();
    // An all-done day with no bonus points only marks the streak.
    const shown = this._historyMatches(all).filter((e) => !(e.kind === "bonus" && !e.points));
    const more = (this._olderHistory ? this._olderMore : this._data.history_more)
      ? `<div class="more-row"><button class="btn" data-history-more ${this._loadingMore ? "disabled" : ""}>${this._loadingMore ? "Loading…" : "Show more"}</button></div>`
      : "";
    if (all.length && !shown.length) return `<p class="empty">Nothing matches. Try another name, type or fewer words.</p>${more}`;
    if (!shown.length) return this._feed([], true);
    const filtered = f.member || f.kind || f.text.trim();
    const count = filtered ? `<p class="muted">${shown.length} of ${all.length}</p>` : "";
    // One heading per day, with what was earned and taken that day.
    const days = [];
    for (const e of shown) {
      const day = localDayOf(e.at);
      if (days.at(-1)?.day !== day) days.push({ day, entries: [] });
      days.at(-1).entries.push(e);
    }
    const groups = days
      .map(({ day, entries }) => {
        const counted = entries.filter((e) => e.review !== "rejected");
        const plus = counted.reduce((n, e) => n + Math.max(0, e.points || 0), 0);
        const minus = counted.reduce((n, e) => n + Math.min(0, e.points || 0), 0);
        const totals = [plus ? `<span class="plus">+${plus}</span>` : "", minus ? `<span class="minus">−${-minus}</span>` : ""].filter(Boolean).join(" · ");
        return `<h3 class="day-head">${esc(dayHeading(day))}${totals ? `<span class="day-totals">${totals}</span>` : ""}</h3>${this._feed(entries, true)}`;
      })
      .join("");
    return count + groups + more;
  }

  async _historyMoreLoad() {
    if (this._loadingMore) return;
    const all = this._historyAll();
    const last = all.at(-1);
    if (!last) return;
    this._loadingMore = true;
    this._refreshHistoryList();
    try {
      const res = await this._ws({ type: `${DOMAIN}/history`, before: last.at, limit: 200 });
      this._olderHistory = [...(this._olderHistory || []), ...res.entries];
      this._olderMore = res.more;
    } catch (err) {
      this._toast(err?.message || String(err), true);
    } finally {
      this._loadingMore = false;
      this._refreshHistoryList();
    }
  }

  _refreshHistoryList() {
    const list = this.shadowRoot.querySelector("[data-history-list]");
    if (list) list.innerHTML = this._historyList();
  }

  // What History shows (with its filters), as a spreadsheet file.
  async _historyCsv() {
    try {
      const res = await this._ws({ type: `${DOMAIN}/history`, limit: 5000 });
      const rows = this._historyMatches(res.entries);
      const head = ["Date", "Time", "Person", "What", "Type", "Points", "Before", "After", "Status", "Why it didn't happen", "By"];
      const lines = rows.map((e) => {
        const d = new Date(e.at);
        const status = e.review === "rejected" ? "Didn't happen" : e.review === "pending" ? "To check" : e.review === "approved" ? "Checked" : e.given === "to_give" ? "To hand out" : e.given === "given" ? "Handed out" : "";
        return [localDayOf(e.at), d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), this._memberById(e.member)?.name || "", e.title, e.kind, e.points, e.before ?? "", e.after ?? "", status, e.reason || "", e.reviewed_by || e.given_by || e.by || ""].map(csvCell).join(",");
      });
      const blob = new Blob([`\ufeff${[head.join(","), ...lines].join("\r\n")}`], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `family-history-${localDayIso(0)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      this._toast(`Downloaded ${rows.length} ${rows.length === 1 ? "row" : "rows"}.`);
    } catch (err) {
      this._toast(err?.message || String(err), true);
    }
  }

  _feed(entries, review = false, balances = false) {
    // An all-done day with no bonus points only marks the streak.
    entries = entries.filter((e) => !(e.kind === "bonus" && !e.points));
    if (!entries.length) return `<p class="empty">Nothing yet. Finished chores and spent points show up here.</p>`;
    return `<ul class="feed">${entries
      .map((e) => {
        const m = this._memberById(e.member);
        const gone = e.review === "rejected";
        const cls = gone ? "gone" : e.points >= 0 ? "plus" : "minus";
        const from = e.kind === "high_five" ? this._memberById(e.from) : null;
        const what = e.kind === "high_five" ? `got a high five ${esc(e.title)} from <b>${esc(from?.name || "someone")}</b>` : e.kind === "chore" ? `did <b>${esc(e.title)}</b>` : e.kind === "reward" ? `got <b>${esc(e.title)}</b>` : e.kind === "bonus" ? `earned a bonus: <b>${esc(e.title)}</b>` : e.kind === "penalty" ? `lost points: <b>${esc(e.title)}</b> didn't happen` : e.kind === "allowance" ? "got their <b>weekly allowance</b>" : e.kind === "saving" ? `earned a <b>saving bonus</b>` : e.kind === "birthday" ? "got <b>birthday points</b> 🎂" : `<b>${esc(e.title)}</b>`;
        const note = gone ? ` · didn't happen${e.reason ? `: ${e.reason}` : ""}` : e.review === "pending" ? " · to check" : e.auto ? " · checked automatically" : e.given === "to_give" ? " · to hand out" : e.given === "to_approve" ? " · waiting for a parent to say yes" : e.kind === "penalty" && e.reason ? ` · ${e.reason}` : "";
        const by = review && (e.reviewed_by || e.given_by || e.by) ? ` · by ${e.reviewed_by || e.given_by || e.by}` : "";
        const balance = (review || balances) && e.before !== undefined && !gone && e.kind !== "high_five";
        const button = !review || e.kind !== "chore" ? "" : gone ? `<button class="btn good" data-review="${esc(e.id)}" data-approved="1">Done right</button>` : `<button class="btn bad" data-didnt="${esc(e.id)}">Didn't happen</button>`;
        return `<li>${m ? this._avatar(m, true) : ""}<span class="what">${esc(m?.name || "Someone")} ${what}<br><small class="muted">${esc(whenText(e.at))}${esc(note)}${esc(by)}</small></span>
          <span class="amount ${cls}">${e.kind === "high_five" ? "" : signed(e.points)}${balance ? `<small class="balance" title="${esc(m?.name || "Their")} points before and after">${e.before} → ${e.after}</small>` : ""}</span>${button}</li>`;
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
    // Someone is typing in the History search: refresh just the list.
    const typing = this.shadowRoot.activeElement;
    if (this._data && this._mode === "parents" && this._tab === "history" && typing?.dataset?.historyText !== undefined) {
      const list = this.shadowRoot.querySelector("[data-history-list]");
      if (list) {
        list.innerHTML = this._historyList();
        return;
      }
    }
    const title = this.shadowRoot.querySelector(".title");
    if (title) title.textContent = this._mode === "parents" ? "Parents" : "Family";
    const main = this.shadowRoot.querySelector("main");
    if (!this._data) {
      main.innerHTML = this._error ? `<p class="error" role="alert">${esc(this._error)}</p>` : `<p class="empty">Loading…</p>`;
      return;
    }
    const error = this._error ? `<p class="error" role="alert">${esc(this._error)}</p>` : "";
    // The Parents / Back to Family button: in the toolbar, or (as a card,
    // which has no toolbar) at the top of the page.
    const slot = this.shadowRoot.querySelector(".switch-slot");
    if (slot) slot.innerHTML = this._switchBar();
    const wall = this._mode !== "parents" && this._isWall();
    main.classList.toggle("wall-main", wall);
    const quiet = !wall && this._isQuiet();
    this._wasQuiet = quiet;
    main.innerHTML = quiet ? this._renderQuiet() : (slot || wall ? "" : this._switchBar()) + error + (this._mode === "parents" ? this._renderParents() : wall ? this._renderWall() : this._renderFamily());
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
    if ((this._sheet?.type === "note" && overlay.querySelector("[data-note-form]")) || (this._sheet?.type === "ask" && overlay.querySelector("[data-ask-form]"))) {
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
    // A child's own phone: always their page, with just what's theirs.
    const phone = this._isPhone();
    if (phone && d.me && this._member !== d.me) this._member = d.me;
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
            const pictures = member?.picture_mode && c.emoji;
            const sayIt = `<button class="say-btn" data-say="${esc(c.name)}" aria-label="Read ${esc(c.name)} aloud" title="Read it to me">🔊</button>`;
            return `<div class="tile chore${pictures ? " pictures" : ""}"${pictures ? ` data-say="${esc(c.name)}"` : ""}>
              ${c.emoji ? `<span class="emoji">${emo(c.emoji)}</span>` : ""}
              <span class="label">${esc(c.name)}</span>${this._timerBit(c)}
              ${(c.list || c.on_list) && !own ? `<span class="sub">${esc(c.list || c.on_list)}</span>` : ""}${c.turn && !member ? `<span class="sub">${esc(this._memberById(c.turn)?.name || "Someone")}'s turn</span>` : c.turn ? `<span class="sub">Your turn</span>` : ""}${c.until_time ? `<span class="sub">Until ${esc(timeText(c.until_time))}</span>` : ""}${who}
              ${c.traded ? `<span class="sub">Traded from ${esc(this._tradeFrom(c.traded))}</span>` : ""}
              ${c.difficulty ? `<span class="sub stars" title="${esc(c.difficulty)}">${"⭐".repeat({ easy: 1, medium: 2, hard: 3 }[c.difficulty] || 0)}</span>` : ""}
              ${c.team ? `<span class="sub">Team: ${(c.team_done || []).length} of ${(c.members || []).length} done</span>` : ""}
              <span class="worth">+${pts(c.points)}</span>${c.boost ? `<span class="sub boost-tag">⚡ ${c.boost}× points</span>` : ""}
              <span class="tile-tools">${c.how || c.example ? `<button class="say-btn" data-how="${esc(c.id)}" aria-label="How to do ${esc(c.name)}" title="How to do it">ⓘ</button>` : ""}${sayIt}${member && fit === "chores" && c.source !== "todo" && !c.list && !c.traded && !this._offered(c.id, member.id) ? `<button class="trade-btn" data-trade-offer="${esc(c.id)}" aria-label="Trade ${esc(c.name)}" title="Trade">⇄</button>` : ""}</span>
              <button class="check" data-chore="${esc(c.id)}" aria-label="${esc(c.name)} is done"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></button></div>`;
          })
          .join("")}</div>`;
    const own = member?.own_today || {};
    const mineBody =
      (mine.length
        ? choreTiles(mine, "chores")
        : `<p class="empty">${own.done ? `All done, ${esc(member.name)}! 🎉` : "Nothing of your own right now."}</p>`) +
      (member ? this._tradesBlock(member) : "");
    const grabBody = grabs.length ? choreTiles(grabs, "grabs") : `<p class="empty">Nothing up for grabs right now.</p>`;
    const visibleRewards = this._visibleRewards(member);
    const rewardTiles = visibleRewards.length
      ? `<div class="tiles" data-fit="rewards">${visibleRewards
          .map((r) => {
            const short = member && member.points < r.points;
            // On hold: no getting it now, but one they can't afford yet can still be saved for.
            const shopDays = r.shop_days || [];
            const notToday = shopDays.length && !shopDays.includes((new Date().getDay() + 6) % 7);
            const used = member && ((r.used_by || []).includes(member.id) || (member.held_until && !short) || (notToday && !short));
            const goal = member && member.goal === r.id;
            const sub = this._rewardSub(r);
            const note = member?.held_until ? "On hold" : used ? AGAIN[r.limit] : short ? `${member.points} of ${r.points} · ${r.points - member.points} more to go` : LIMIT_TEXT[r.limit] || "";
            const bar = short && !used ? this._bar(member.points, r.points) : "";
            // Not enough yet: a tap offers to save up for it.
            return `<button class="tile${short ? " short" : ""}${goal ? " goal" : ""}" data-reward="${esc(r.id)}" ${used ? "disabled" : ""}>
              ${goal ? `<span class="sub goal-tag">🎯 Saving for this</span>` : member && (member.wishes || []).includes(r.id) ? `<span class="sub goal-tag">♥ On your wishlist</span>` : ""}
              ${r.emoji ? `<span class="emoji">${emo(r.emoji)}</span>` : ""}
              <span class="label">${esc(r.name)}</span>${sub ? `<span class="sub">${esc(sub)}</span>` : ""}
              <span class="worth">${pts(r.points)}</span>
              ${bar}${note ? `<span class="sub">${esc(note)}</span>` : ""}${shopDays.length ? `<span class="sub shop-day">🛒 ${notToday ? "Shop day" : "Shop day today"}: ${esc(shopDays.map((i) => DAYS[i]).join(", "))}</span>` : ""}</button>`;
          })
          .join("")}</div>`
      : `<p class="empty">${d.rewards.length ? (member ? `No rewards for ${esc(member.name)} right now.` : "No rewards for everyone right now.") : "No rewards yet. A parent adds them on the <b>Parents</b> dashboard."}</p>`;
    const cashTile =
      member && d.money
        ? `<button class="tile cashout" data-cash-out ${member.held_until ? "disabled" : ""}><span class="emoji">💰</span><span class="label">Cash out</span><span class="sub">${esc(money(member.points, d.money))} in points</span></button>`
        : "";
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
    const goingFor = [...this._familyGoalTiles(member), this._savingTile(member), this._freezeTile(member), this._giveTile(member), this._bankTile(member), this._giftTile(member), ...(member ? this._goingFor(member) : []), ...this._raceTiles(member)].filter(Boolean);
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
    const countdowns = (d.countdowns || []).filter((c) => !member || !c.member || c.member === member.id);
    const vote = d.vote && (d.vote.status === "open" || d.vote.winner != null) ? d.vote : null;
    const tomorrow = this._tomorrowBody(member);
    const links = (d.links || []).filter((l) => !member || !l.member || l.member === member.id);
    const screens = d.screen || [];
    const weather = d.weather;
    const bingo = member ? d.bingo?.[member.id] : null;
    const sections = {
      bingo: bingo ? this._section("bingo", "Chore bingo", this._bingoBody(bingo)) : "",
      quests: this._questsBody(member),
      pets: this._petsBody(member),
      auctions: this._auctionsBody(member),
      market: this._marketBody(member),
      theme: this._themeBody(member),
      reading: this._readingBody(member),
      mood: member && d.mood_check ? this._section("mood", "How was today?", this._moodBody(member)) : "",
      weather: weather ? this._section("weather", "What to wear", `<div class="tiles" data-fit="weather">${this._weatherTile(weather)}</div>`) : "",
      tomorrow: tomorrow ? this._section("tomorrow", "Tomorrow", tomorrow.body, tomorrow.count) : "",
      links: links.length ? this._section("links", "Links", `<div class="tiles" data-fit="links">${links.map((l) => `<button class="tile link" data-link="${esc(l.id)}"><span class="emoji">${emo(l.emoji, "🔗")}</span><span class="label">${esc(l.name)}</span></button>`).join("")}</div>`, links.length) : "",
      screen: screens.length ? this._section("screen", "Screen time left", `<div class="tiles" data-fit="screen" data-screen-tiles>${this._screenTiles()}</div>`) : "",
      countdowns: countdowns.length ? this._section("countdowns", "Coming up", `<div class="tiles" data-fit="countdowns">${countdowns.map((c) => this._countdownTile(c)).join("")}</div>`, countdowns.length) : "",
      vote: vote ? this._section("vote", vote.status === "open" ? "What's for dinner?" : "Dinner", this._voteBody(vote, member)) : "",
      going: goingFor.length ? this._section("going", "Going for", `<div class="tiles going" data-fit="going">${goingFor.join("")}</div>`) : "",
      chores: member && (mine.length || (own.total && !hide) || this._tradesFor(member).length) ? this._section("chores", "My chores", mineBody, mine.length) : "",
      grabs: grabs.length || (!member && !hide) ? this._section("grabs", "Up for grabs", grabBody, grabs.length) : "",
      pick: this._pickBody(member),
      claims: (d.claims || []).length ? this._section("claims", "Who did this?", `<div class="tiles" data-fit="claims">${d.claims.map((c) => `<button class="tile claim" data-claim="${esc(c.id)}"><span class="emoji">${emo(c.emoji, "🤖")}</span><span class="label">${esc(c.name)}</span><span class="worth">+${pts(c.points)}</span><span class="sub">Done by a device. Was it you?</span></button>`).join("")}</div>`, d.claims.length) : "",
      routines: routines.length ? this._section("routines", "Routines", `<div class="tiles" data-fit="routines">${routines.map((r) => this._routineTile(r, member)).join("")}</div>`, routines.length) : "",
      notes: this._section("notes", "Notes", noteTiles, notes.length),
      today: events.length || (d.has_calendars && !hide) ? this._section("today", "Today", eventTiles, events.length, `<button class="btn sec-extra" data-days>Next few days</button>`) : "",
      meals: meals.length ? this._section("meals", "Meals", mealTiles) : "",
      done: done.length ? this._section("done", "Done today", doneTiles, done.length) : "",
      rewards: visibleRewards.length || cashTile || member || !hide ? this._section("rewards", "Rewards", this._requestTiles(member) + (member?.held_until ? `<p class="hold-note">⏸ Rewards are on hold until ${esc(holdText(member.held_until))}${member.hold_reason ? ` · ${esc(member.hold_reason)}` : ""}. Chores still earn points.</p>` : "") + (cashTile && visibleRewards.length ? rewardTiles.replace('data-fit="rewards">', `data-fit="rewards">${cashTile}`) : cashTile ? `<div class="tiles" data-fit="rewards">${cashTile}</div>` : rewardTiles), visibleRewards.length) : "",
      home,
      lately: feed.length || !hide ? this._section("lately", "Lately", `<div data-fit="lately">${this._feed(feed.slice(0, 10))}</div>`) : "",
    };
    const badges = member && (member.badges || []).length
      ? `<div class="badges" aria-label="Badges">${member.badges.map((b) => `<span class="badge-pill" title="${esc(b.text)}">${esc(b.emoji)} ${esc(b.name)}</span>`).join("")}</div>`
      : "";
    const streak = d.family_streak ? `<span class="family-streak" title="Days in a row everyone finished their own chores">🔥 Family streak: ${d.family_streak} ${d.family_streak === 1 ? "day" : "days"}${d.family_streak >= 7 ? " 🏅" : ""}</span>` : "";
    const personal = member
      ? `<button class="pill-btn" data-story="${esc(member.id)}" title="See your points story">⭐ ${esc(pts(member.points))}</button>${d.members.length > 1 ? `<button class="pill-btn" data-high-five="${esc(member.id)}">🙌 High five</button>` : ""}`
      : "";
    const extras = personal || streak ? `<div class="head-extras">${personal}${streak}</div>` : "";
    return `${this._banners(member)}<h2>${member ? `${member.birthday_today ? `Happy birthday, ${esc(member.name)}! 🎂` : `Hi ${esc(member.name)}!`}${cash}` : "Who's here?"}</h2>${extras}${badges}
      ${phone && member ? "" : this._people(this._pinnedMember() ? [this._pinnedMember()] : d.members, "data-member", this._member)}
      ${sectionOrder(d.section_order).filter((key) => !phone || !member || PHONE_SECTIONS.includes(key)).map((key) => sections[key] || "").join("")}`;
  }

  // Away, double points and birthdays, across the top of the Family page.
  _banners(member) {
    const d = this._data;
    const rows = [];
    const away = d.away?.now;
    if (away) rows.push(`<p class="banner away">🏖️ The family is away${away.until ? ` until ${esc(dayText(away.until, -1))}` : ""}. Chores are off: enjoy it!</p>`);
    for (const b of (d.boosts || []).filter((x) => x.on)) {
      const which = b.chores?.length ? "on some chores" : "on every chore";
      rows.push(`<p class="banner boost">⚡ <b>${esc(b.label)}</b>: ${b.factor}× points ${which} until ${esc(untilText(b.until))}</p>`);
    }
    const leave = this._leaveBanner();
    if (leave) rows.push(leave);
    const birthdays = d.members.filter((m) => m.birthday_today && (!member || m.id !== member.id));
    if (birthdays.length) rows.push(`<p class="banner birthday">🎂 Happy birthday, ${esc(namesText(birthdays.map((m) => m.name)))}!</p>`);
    return rows.join("");
  }

  // Time to leave in the morning: a countdown across the top.
  _leaveBanner() {
    const left = leaveMinutes(this._data?.leave);
    if (left == null) return "";
    const at = timeText(this._data.leave.at.slice(11, 16));
    const text = left > 1 ? `Leave in ${left} minutes (${at})` : left >= 0 ? `Time to go! (${at})` : `Time to go! It was ${at}.`;
    return `<p class="banner leave${left <= 5 ? " now" : ""}" data-leave>🎒 ${esc(text)}</p>`;
  }

  // The week's 3×3 board: a square is marked when its chore is done.
  _bingoBody(board) {
    const cells = board.cells.map((c) => `<div class="bingo-cell${c.done ? " done" : ""}"><span class="emoji">${emo(c.emoji, "⬜")}</span><span class="label">${esc(c.name)}</span>${c.done ? `<span class="tick" aria-hidden="true">✓</span>` : ""}</div>`).join("");
    const reward = [board.line_points ? `+${pts(board.line_points)} a line` : "", board.full_points ? `+${pts(board.full_points)} for the whole card` : ""].filter(Boolean).join(", ");
    return `<div class="bingo-grid">${cells}</div>
      <p class="muted">${board.full ? "🎉 The whole card! " : board.lines ? `${board.lines} ${board.lines === 1 ? "line" : "lines"} so far. ` : ""}Rows, columns and diagonals count${reward ? `: ${esc(reward)}` : ""}. A new card every Monday.</p>`;
  }

  // A streak about to break (a sick day): freeze it for some points.
  _freezeTile(member) {
    const days = member?.freeze_offers || [];
    if (!days.length || !this._data.freeze_cost) return "";
    const today = new Date().toISOString().slice(0, 10);
    return `<div class="tile going-tile freeze"><span class="emoji">❄️</span><span class="label">Save your streak</span>
      <span class="sub">Sick, or a busy day? A streak freeze makes it a day off, for ${pts(this._data.freeze_cost)}. One a week.</span>
      <span class="freeze-btns">${days.map((day) => `<button class="btn" data-freeze="${esc(day)}" ${member.points < this._data.freeze_cost ? "disabled" : ""}>${day === today ? "Freeze today" : "Freeze yesterday"}</button>`).join("")}</span></div>`;
  }

  // Quests: bigger jobs in steps, done in order.
  _questsBody(member) {
    const quests = (this._data.quests || []).filter((q) => !member || !q.members || q.members.includes(member.id));
    if (!quests.length) return "";
    const tiles = quests.map((q) => {
      const steps = q.steps.map((st, i) => {
        const done = q.done[i];
        const who = done ? this._memberById(done.member) : null;
        if (done) return `<li class="done">✓ ${esc(st.name)}<small>${who ? ` · ${esc(who.name)}` : ""}</small></li>`;
        if (i === q.next) return `<li class="next"><button class="btn primary" data-quest="${esc(q.id)}">Done: ${esc(st.name)}${st.points ? ` +${pts(st.points)}` : ""}</button></li>`;
        return `<li class="later">🔒 ${esc(st.name)}</li>`;
      }).join("");
      return `<div class="tile quest${q.finished ? " won" : ""}"><span class="emoji">${emo(q.emoji, "🗺️")}</span><span class="label">${esc(q.name)}</span>
        ${this._bar(q.done.length, q.steps.length)}<ol class="quest-steps">${steps}</ol>${q.finished ? `<span class="sub">Quest complete! 🎉</span>` : ""}</div>`;
    }).join("");
    return this._section("quests", "Quests", `<div class="tiles quests" data-fit="quests">${tiles}</div>`, quests.length);
  }

  // Pets: today's meals (or walks), done once each.
  _petsBody(member) {
    const pets = (this._data.pets || []).filter((p) => !member || !p.members || p.members.includes(member.id));
    if (!pets.length) return "";
    const tiles = pets.map((p) => {
      const slots = p.slots.map((slot, i) => {
        const who = slot.done_by ? this._memberById(slot.done_by) : null;
        if (slot.done_by) return `<li class="done">✓ ${esc(timeText(slot.time))}<small> · ${esc(who?.name || "Someone")} at ${esc(timeText(slot.done_at.slice(11, 16)))}</small></li>`;
        if (slot.due) return `<li><button class="btn${slot.late ? " bad" : " primary"}" data-pet="${esc(p.id)}" data-slot="${i}">${esc(p.task)} · ${esc(timeText(slot.time))}${slot.late ? " (late)" : ""}</button></li>`;
        return `<li class="later">${esc(timeText(slot.time))}</li>`;
      }).join("");
      return `<div class="tile pet"><span class="emoji">${emo(p.emoji, "🐾")}</span><span class="label">${esc(p.name)}</span><ul class="pet-slots">${slots}</ul>${p.points ? `<span class="sub">+${pts(p.points)} each time</span>` : ""}</div>`;
    }).join("");
    return this._section("pets", "Pets", `<div class="tiles pets" data-fit="pets">${tiles}</div>`, pets.length);
  }

  // The shared screen at rest (quiet hours): a clock, time to leave and notes.
  _isQuiet() {
    const q = this._data?.quiet;
    if (!q || this._mode === "parents" || Date.now() - (this._lastTouch || 0) < IDLE_MS) return false;
    const now = new Date();
    const minutes = now.getHours() * 60 + now.getMinutes();
    const at = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
    const from = at(q.from);
    const until = at(q.until);
    return from <= until ? minutes >= from && minutes < until : minutes >= from || minutes < until;
  }

  _renderQuiet() {
    const d = this._data;
    const now = new Date();
    const notes = (d.notes || []).filter((n) => !n.member).slice(0, 3);
    return `<div class="quiet" data-wake>
      <div class="quiet-clock">${esc(now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }))}</div>
      <div class="quiet-day">${esc(now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }))}</div>
      ${this._leaveBanner()}
      ${notes.map((n) => `<p class="quiet-note">${esc(n.text)}</p>`).join("")}
      <p class="quiet-hint">Tap to wake</p></div>`;
  }

  // The evening check-in: one tap for how today was.
  _moodBody(member) {
    return `<div class="moods">${MOODS.map(([id, emoji, label]) => `<button class="mood${member.mood_today === id ? " on" : ""}" data-mood="${id}" aria-pressed="${member.mood_today === id}"><span class="emoji">${emoji}</span><span>${label}</span></button>`).join("")}</div>
      <p class="muted">Only parents see these.</p>`;
  }

  // The give jar: what the family gives for, and (on someone's page) giving.
  _giveTile(member) {
    const g = this._data.give;
    if (!g) return "";
    const mine = member ? g.by?.[member.id] || 0 : 0;
    const inner = `<span class="emoji">${emo(g.emoji, "💝")}</span><span class="label">${esc(g.name)}</span>${this._bar(g.total, g.target)}
      <span class="sub">${g.reached ? "We did it! 🎉" : `${g.total} of ${g.target} points given`}${member && mine ? ` · ${mine} from you` : ""}</span>`;
    return member ? `<button class="tile going-tile give" data-give>${inner}<span class="sub">Tap to give points</span></button>` : `<div class="tile going-tile give">${inner}</div>`;
  }

  // Races: "Race someone", and today's races with whoever won.
  _raceTiles(member) {
    const d = this._data;
    if (!member || !d.challenge_points) return [];
    const tiles = (d.challenges || []).filter((c) => c.members.includes(member.id)).map((c) => {
      const other = this._memberById(c.members.find((id) => id !== member.id));
      const won = c.winner === member.id;
      const text = c.winner ? (won ? `You won the race with ${other?.name || "them"}! +${pts(c.points)}` : `${other?.name || "They"} won this one`) : `Racing ${other?.name || "someone"}: first to finish today's chores wins +${pts(c.points)}`;
      return `<div class="tile going-tile${won ? " won" : ""}"><span class="emoji">${c.winner ? (won ? "🏆" : "🏁") : "🏃"}</span><span class="label">${esc(text)}</span></div>`;
    });
    const others = d.members.filter((m) => m.id !== member.id && m.own_today?.left);
    if ((member.own_today || {}).left && others.length) {
      tiles.push(`<button class="tile going-tile" data-race><span class="emoji">🏁</span><span class="label">Race someone</span><span class="sub">First to finish today's own chores gets +${pts(d.challenge_points)}</span></button>`);
    }
    return tiles;
  }

  // Pick your chores: whose turn it is, the chores left in the pool, and
  // (on someone's page) the ones they picked.
  _pickBody(member) {
    const picks = this._data.picks;
    if (!picks) return "";
    const next = this._memberById(picks.next);
    const left = picks.pool.filter((c) => !c.picked_by);
    const mine = member ? picks.pool.filter((c) => c.picked_by === member.id) : picks.pool.filter((c) => c.picked_by);
    if (!left.length && !mine.length) return "";
    const turn = next
      ? `<p class="pick-turn">${this._avatar(next, true)}<span><b>${esc(next.name)}</b>, it's your turn to pick${picks.target ? ` (up to ${pts(picks.target)} each this week)` : ""}.</span></p>`
      : `<p class="pick-turn">All picked for this week.</p>`;
    const tiles = [
      ...left.map((c) => {
        const allowed = next && (!c.members.length || c.members.includes(next.id));
        return `<button class="tile pick" data-pick="${esc(c.id)}" ${allowed ? "" : "disabled"}><span class="emoji">${emo(c.emoji, "🧹")}</span><span class="label">${esc(c.name)}</span><span class="worth">+${pts(c.points)}</span>${allowed ? `<span class="sub">Tap to pick it</span>` : ""}</button>`;
      }),
      ...mine.map((c) => {
        const m = this._memberById(c.picked_by);
        return `<div class="tile pick picked"${m ? ` style="--c:${esc(m.color)}"` : ""}><span class="emoji">${emo(c.emoji, "🧹")}</span><span class="label">${esc(c.name)}</span><span class="worth">+${pts(c.points)}</span><span class="sub">${esc(m ? `${m.name}'s this week` : "Picked")}</span></div>`;
      }),
    ];
    return this._section("pick", "Pick your chores", `${turn}<div class="tiles" data-fit="pick">${tiles.join("")}</div>`, left.length);
  }

  // The wall view: for a TV or a tablet on the wall, read from across the
  // room. A card with `wall: true`, or the Family page at #wall.
  // A child's own phone view: `#me` on the Family page, or a card with
  // `phone: true`. Shows their page only (who's logged in), with fewer sections.
  _isPhone() {
    if (this._config?.phone) return true;
    try {
      return window.location.hash === "#me";
    } catch (_err) {
      return false;
    }
  }

  _isWall() {
    if (this._config?.wall) return true;
    try {
      return window.location.hash === "#wall";
    } catch (_err) {
      return false;
    }
  }

  _renderWall() {
    const d = this._data;
    const now = new Date();
    const columns = d.members.map((m) => {
      const open = d.chores.filter((c) => !c.grab && c.can.includes(m.id));
      const done = (d.done_today || []).filter((e) => e.member === m.id && e.kind === "chore");
      const own = m.own_today || { total: 0, left: 0 };
      const finished = own.total ? own.total - own.left : 0;
      return `<section class="wall-col" style="--c:${esc(m.color)}">
        <div class="wall-who">${this._avatar(m)}<div><div class="wall-name">${esc(m.name)}</div><div class="wall-points">⭐ ${esc(pts(m.points))}</div></div></div>
        ${own.total ? `<div class="wall-progress">${this._bar(finished, own.total)}<span>${own.left ? `${finished} of ${own.total}` : "All done! 🎉"}</span></div>` : ""}
        <ul class="wall-list">
          ${open.map((c) => `<li><span class="wall-mark">○</span>${emo(c.emoji)} ${esc(c.name)}</li>`).join("")}
          ${done.map((e) => `<li class="done"><span class="wall-mark">✓</span><span class="wall-done">${esc(e.title)}</span></li>`).join("")}
          ${!open.length && !done.length ? `<li class="muted">Nothing today</li>` : ""}
        </ul></section>`;
    });
    const grabs = d.chores.filter((c) => c.grab);
    const events = d.today || [];
    return `<div class="wall">${this._leaveBanner()}
      <header class="wall-head"><h1>${esc(now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }))}</h1>
        ${d.family_streak ? `<span class="wall-streak">🔥 ${d.family_streak} ${d.family_streak === 1 ? "day" : "days"} in a row</span>` : ""}</header>
      <div class="wall-cols">${columns.join("")}</div>
      ${grabs.length ? `<p class="wall-extra">Up for grabs: ${grabs.map((c) => `${emo(c.emoji)} ${esc(c.name)} +${pts(c.points)}`).join(" · ")}</p>` : ""}
      ${events.length ? `<p class="wall-extra">Today: ${events.map((e) => `${esc(eventTime(e))} ${esc(e.title)}`).join(" · ")}</p>` : ""}
    </div>`;
  }

  _countdownTile(c) {
    const m = this._memberById(c.member);
    return `<div class="tile countdown${c.days <= 0 ? " won" : ""}"${m ? ` style="--c:${esc(m.color)}"` : ""}>
      <span class="emoji">${emo(c.emoji, "📅")}</span><span class="label">${esc(c.name)}</span>
      <span class="worth">${esc(daysLeftText(c.days))}</span>
      <span class="sub">${esc(dayText(c.date, -1))}</span></div>`;
  }

  // The dinner vote: tap a choice (on everyone's page, then who's voting).
  _voteBody(vote, member) {
    const day = vote.day === localDayIso(0) ? "tonight" : `on ${dayText(vote.day, -1)}`;
    if (vote.status !== "open") {
      return `<div class="tiles"><div class="tile won"><span class="emoji">🍽️</span><span class="label">${esc(vote.options[vote.winner])}</span><span class="sub">Dinner ${esc(day)}: it won the vote</span></div></div>`;
    }
    const mine = member ? vote.votes?.[member.id] : undefined;
    const total = (vote.counts || []).reduce((a, b) => a + b, 0);
    return `<p class="muted">${esc(`Vote for dinner ${day}`)}${vote.closes ? `, until ${esc(timeText(vote.closes))}` : ""}. ${total} ${total === 1 ? "vote" : "votes"} so far.</p>
      <div class="tiles" data-fit="vote">${vote.options
        .map((name, i) => {
          const who = Object.entries(vote.votes || {}).filter(([, o]) => o === i).map(([id]) => this._memberById(id)).filter(Boolean);
          return `<button class="tile vote${mine === i ? " goal" : ""}" data-vote-option="${i}">
            ${mine === i ? `<span class="sub goal-tag">✓ Your vote</span>` : ""}<span class="label">${esc(name)}</span>
            <span class="worth">${vote.counts?.[i] || 0}</span>${who.length ? `<span class="who">${who.map((m) => this._avatar(m, true)).join("")}</span>` : ""}</button>`;
        })
        .join("")}</div>`;
  }

  // Someone's own page: ask for a reward that isn't on the list, and how
  // their asks are going.
  _requestTiles(member) {
    if (!member) return "";
    const mine = (this._data.requests || []).filter((r) => r.member === member.id);
    const tiles = mine.map((r) => {
      const status = r.status === "pending" ? "Waiting for a parent" : r.status === "approved" ? `Yes! ${pts(r.points)}, in your rewards` : "Not this time";
      return `<div class="tile request ${esc(r.status)}"><span class="emoji">${emo(r.emoji, "🙏")}</span><span class="label">${esc(r.name)}</span>
        <span class="sub">${esc(status)}</span>${r.status === "pending" ? `<button class="note-x" data-request-cancel="${esc(r.id)}" aria-label="Take back ${esc(r.name)}">✕</button>` : ""}</div>`;
    });
    const ideas = (this._data.chore_ideas || []).filter((i) => i.member === member.id).map((i) => {
      const status = i.status === "pending" ? "Waiting for a parent" : i.status === "approved" ? `Yes! ${pts(i.points)}, in your chores` : "Not this time";
      return `<div class="tile request ${esc(i.status)}"><span class="emoji">${emo(i.emoji, "🧽")}</span><span class="label">${esc(i.name)}</span>
        <span class="sub">${esc(status)}</span>${i.status === "pending" ? `<button class="note-x" data-idea-cancel="${esc(i.id)}" aria-label="Take back ${esc(i.name)}">✕</button>` : ""}</div>`;
    });
    return `<div class="tiles requests"><button class="tile ask" data-ask><span class="emoji">🙏</span><span class="label">Ask for something</span><span class="sub">A parent says yes or no</span></button>
      <button class="tile ask" data-offer><span class="emoji">🧽</span><span class="label">Offer to do a chore</span><span class="sub">For points, if a parent says yes</span></button>${tiles.join("")}${ideas.join("")}</div>`;
  }

  _badgeToast(member, badges) {
    if (!badges?.length) return;
    setTimeout(() => this._toast(`🏅 New badge for ${member.name}: ${badges.map((b) => `${b.emoji} ${b.name}`).join(", ")}!`), 3600);
  }

  _tradeFrom(tradeId) {
    const t = (this._data.trades || []).find((x) => x.id === tradeId);
    return t?.from_name || "someone";
  }

  _offered(choreId, memberId) {
    return (this._data.trades || []).some((t) => t.chore_id === choreId && t.from === memberId);
  }

  // Trades that matter on someone's page: theirs, and offers they could take.
  _tradesFor(member) {
    return (this._data.trades || []).filter(
      (t) => t.status !== "approved" && (t.from === member.id || t.to === member.id || (t.status === "offered" && !t.to)),
    );
  }

  _tradesBlock(member) {
    const rows = this._tradesFor(member).map((t) => {
      const chore = `${t.emoji ? `${emo(t.emoji)} ` : ""}<b>${esc(t.chore)}</b> +${pts(t.points)}${t.pay ? ` <span class="pay">and ${pts(t.pay)} paid</span>` : ""}`;
      if (t.from === member.id) {
        const taker = t.to ? this._memberById(t.to)?.name || "someone" : "anyone";
        const text = t.status === "taken" ? `${esc(taker)} took it · waiting for a parent` : `Offered to ${esc(taker)}`;
        return `<li><span class="grow">${chore}<small>${text}</small></span><button class="btn" data-trade-cancel="${esc(t.id)}">Take back</button></li>`;
      }
      if (t.status === "taken") {
        return `<li><span class="grow">${chore}<small>From ${esc(t.from_name)} · waiting for a parent</small></span></li>`;
      }
      return `<li><span class="grow">${chore}<small>${esc(t.from_name)} wants to trade it</small></span><button class="btn primary" data-trade-take="${esc(t.id)}">Take it</button></li>`;
    });
    return rows.length ? `<h3 class="trades-head">Trades</h3><ul class="rows trades">${rows.join("")}</ul>` : "";
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
    return `<button class="tile routine-tile${finished ? " won" : ""}" data-routine="${esc(r.id)}"><span class="emoji">${emo(r.emoji, "📋")}</span>
      <span class="label">${esc(r.name)}</span>${people}${r.points ? `<span class="worth">+${pts(r.points)}</span>` : ""}</button>`;
  }

  _routineSheet() {
    const s = this._sheet;
    const r = (this._data.routines || []).find((x) => x.id === s.id);
    if (!r) return "";
    const head = `<h3>${emo(r.emoji, "📋")} ${esc(r.name)}</h3>`;
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
        <span class="box" aria-hidden="true">${ticked.has(i) ? "✓" : ""}</span><span>${esc(text)}</span></button><button class="say-btn" data-say="${esc(text)}" aria-label="Read it aloud" title="Read it to me">🔊</button></li>`)
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
  _familyGoalTiles(member) {
    const goals = (this._data.family_goals || (this._data.family_goal ? [this._data.family_goal] : []))
      .filter((g) => !member || !g.who || g.who.includes(member.id));
    return goals.map((g) => {
      const left = Math.max(0, g.target - g.progress);
      return `<div class="tile going-tile${g.reached ? " won" : ""}"><span class="emoji">${emo(g.emoji, g.reached ? "🎉" : "🏆")}</span>
      <span class="label">${g.reached ? `We did it: ${esc(g.name)}!` : esc(g.name)}</span>
      ${this._bar(g.progress, g.target)}
      ${!g.reached && g.milestone ? `<span class="sub milestone">${{ 25: "A quarter of the way! 🎈", 50: "Halfway there! 🎉", 75: "Three quarters done! 🚀" }[g.milestone] || ""}</span>` : ""}
      <span class="sub">${g.reached ? (g.kids ? "The kids' chores got us there." : "Everyone's chores got us there.") : `${g.kids ? "Just the kids" : g.who ? esc(namesText(g.who.map((id) => this._memberById(id)?.name).filter(Boolean))) : "Together"}: ${g.progress} of ${g.target} points · ${left} to go`}</span></div>`;
    });
  }

  // The saving bonus they'd get by keeping their points until it's given.
  _savingTile(member) {
    const next = this._data.saving_next;
    const points = member ? next?.points?.[member.id] : 0;
    if (!points) return "";
    return `<div class="tile going-tile saving"><span class="emoji">🐷</span><span class="label">Keep your points</span><span class="worth">+${pts(points)}</span>
      <span class="sub">on ${esc(WEEKDAY_NAMES[next.weekday] || "allowance day")}, ${next.percent}% of what you still have then</span></div>`;
  }

  // Saved TV minutes (the screen-time bank), with a button to use some.
  _bankTile(member) {
    const bank = this._data.bank || {};
    if (!member || !(member.id in bank)) return "";
    const minutes = bank[member.id] || 0;
    return `<button class="tile going-tile bank" data-bank ${minutes ? "" : "disabled"}><span class="emoji">🏦</span><span class="label">Saved TV time</span>
      <span class="worth">${minutes} min</span><span class="sub">${minutes ? "Tap to use some today" : "Minutes your TV has left at night are saved here"}</span></button>`;
  }

  // Their gift ideas, for grandparents and birthdays.
  _giftTile(member) {
    if (!member) return "";
    const ideas = member.gift_ideas || [];
    return `<button class="tile going-tile gifts" data-gifts><span class="emoji">🎁</span><span class="label">Gift ideas</span>
      <span class="sub">${ideas.length ? `${ideas.length} on your list` : "Add what you'd like for your birthday"}</span></button>`;
  }

  // Chores up for auction: the lowest bid does it.
  _auctionsBody(member) {
    const now = Date.now();
    const auctions = (this._data.auctions || []).filter((a) => !member || !a.members || a.members.includes(member.id));
    if (!auctions.length) return "";
    const tiles = auctions.map((a) => {
      if (a.status !== "open") {
        const who = a.winner ? this._memberById(a.winner)?.name || "Someone" : null;
        return `<div class="tile auction won"><span class="emoji">${emo(a.emoji, "🔨")}</span><span class="label">${esc(a.name)}</span>
          <span class="sub">${who ? `Sold to ${esc(who)} for ${pts(a.won_for)}` : "Nobody bid"}</span></div>`;
      }
      const mins = Math.max(0, Math.round((new Date(a.closes).getTime() - now) / 60000));
      const mine = member ? a.bids?.[member.id] : null;
      return `<button class="tile auction" data-auction="${esc(a.id)}"><span class="emoji">${emo(a.emoji, "🔨")}</span><span class="label">${esc(a.name)}</span>
        <span class="worth">up to ${pts(a.points)}</span>
        <span class="sub">${a.lowest != null ? `Lowest bid ${pts(a.lowest)}` : "No bids yet"} · ${mins < 60 ? `${mins} min left` : `closes ${esc(timeText(a.closes.slice(11, 16)))}`}</span>
        ${mine != null ? `<span class="sub">Your bid: ${pts(mine)}</span>` : `<span class="sub">Tap to bid</span>`}</button>`;
    }).join("");
    return this._section("auctions", "Chore auctions", `<p class="muted small">Bid how few points you'd do it for. The lowest bid when time's up gets the chore.</p><div class="tiles" data-fit="auctions">${tiles}</div>`, auctions.length);
  }

  // The reading log: tap to log minutes read.
  _readingBody(member) {
    const rule = this._data.reading;
    const homework = this._data.homework;
    if (!rule && !homework) return "";
    const tiles = [rule ? this._readingTile(member, rule) : "", homework ? this._homeworkTile(member, homework) : ""].join("");
    return this._section("reading", rule && homework ? "Reading and homework" : rule ? "Reading" : "Homework", `<div class="tiles" data-fit="reading">${tiles}</div>`);
  }

  // Chores offered to anyone: everyone's page lists them all.
  _marketBody(member) {
    const offers = (this._data.trades || []).filter((t) => t.status === "offered" && (!t.to || (member && t.to === member.id)) && (!member || t.from !== member.id));
    if (!offers.length) return "";
    const tiles = offers.map((t) => `<button class="tile market" data-market-take="${esc(t.id)}"><span class="emoji">${emo(t.emoji, "🔁")}</span><span class="label">${esc(t.chore)}</span>
      <span class="worth">+${pts(t.points)}${t.pay ? ` and ${pts(t.pay)}` : ""}</span><span class="sub">From ${esc(t.from_name)}${t.until ? " · through Sunday" : " · today"}</span><span class="sub">Tap to take it</span></button>`).join("");
    return this._section("market", "Swap market", `<div class="tiles" data-fit="market">${tiles}</div>`, offers.length);
  }

  // The theme week: tap when you kept it today.
  _themeBody(member) {
    const t = this._data.theme;
    if (!t) return "";
    const kept = t.kept || [];
    const done = member && kept.includes(member.id);
    const names = kept.map((id) => this._memberById(id)?.name).filter(Boolean);
    const tile = `<button class="tile theme${done ? " won" : ""}" data-theme-keep ${done ? "disabled" : ""}><span class="emoji">${emo(t.emoji, "🌟")}</span><span class="label">${esc(t.name)}</span>
      ${t.points ? `<span class="worth">+${pts(t.points)} a day</span>` : ""}
      <span class="sub">${done ? "You kept it today!" : member ? "Tap if you kept it today" : names.length ? `Kept it today: ${esc(namesText(names))}` : "Tap if you kept it today"}</span>
      <span class="sub">Until ${esc(dayText(t.until, -1))}</span></button>`;
    return this._section("theme", "Theme week", `<div class="tiles" data-fit="theme">${tile}</div>`);
  }

  // The homework timer: start when they sit down, stop when they're done.
  _homeworkTile(member, rule) {
    const running = member ? this._focus?.[member.id] : null;
    const done = member ? (this._data.homework_today || {})[member.id] || 0 : 0;
    if (running) {
      const minutes = Math.floor((Date.now() - running) / 60000);
      return `<button class="tile homework running" data-homework-stop><span class="emoji">⏱️</span><span class="label">Homework: ${minutes} min</span><span class="sub">Tap when you're done</span></button>`;
    }
    return `<button class="tile homework" data-homework-start><span class="emoji">⏱️</span><span class="label">Homework timer</span>
      <span class="worth">+${pts(rule.points)}</span><span class="sub">every ${rule.block_minutes} min${member ? ` · ${done} min today` : ""}</span></button>`;
  }

  _readingTile(member, rule) {
    const minutes = (who) => (this._data.reading_today || {})[who] || 0;
    const sub = member ? `${minutes(member.id)} min today` : `+${pts(rule.points)} for every ${rule.block_minutes} min`;
    return `<button class="tile reading" data-reading><span class="emoji">📚</span><span class="label">Log reading</span>
      <span class="worth">+${pts(rule.points)}</span><span class="sub">every ${rule.block_minutes} min · ${esc(sub)}</span></button>`;
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
      // A parent's match pays part of it: they need less of their own.
      const match = matchPoints(goal.points, this._data.goal_match || 0);
      const need = goal.points - match;
      tiles.push(`<button class="tile going-tile" data-reward="${esc(goal.id)}"><span class="emoji">${emo(goal.emoji, "🎯")}</span>
        <span class="label">Saving for ${esc(goal.name)}</span>${this._bar(member.points, need)}
        <span class="sub">${member.points >= need ? "You have enough! Tap to get it." : `${member.points} of ${need} · ${need - member.points} more to go`}${match ? ` · a parent adds ${match}` : ""}</span></button>`);
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
  // A chore's timer: Start, the time left while it runs, or Time's up.
  _timerBit(c) {
    if (!c.timer_minutes) return "";
    const timer = this._timers?.[c.id];
    if (!timer) {
      return `<button class="timer-btn" data-timer="${esc(c.id)}" title="Start the timer${c.timer_bonus ? `: finish in time for +${pts(c.timer_bonus)}` : ""}">⏱ ${c.timer_minutes} min${c.timer_bonus ? ` · +${c.timer_bonus}` : ""}</button>`;
    }
    const left = Math.round((timer.start + c.timer_minutes * 60000 - Date.now()) / 1000);
    return `<span class="timer-run${left <= 0 ? " up" : ""}" data-timer-left="${esc(c.id)}">${left <= 0 ? "Time's up!" : `⏱ ${clockText(left)}`}</span><button class="timer-stop" data-timer-stop="${esc(c.id)}" aria-label="Stop the timer">✕</button>`;
  }

  _startTimer(choreId) {
    const chore = (this._data.chores || []).find((c) => c.id === choreId);
    if (!chore?.timer_minutes) return;
    this._timers ||= {};
    this._timers[choreId] = { start: Date.now(), minutes: chore.timer_minutes, done: false };
    this._render();
    if (!this._timerTick) {
      this._timerTick = setInterval(() => this._tickTimers(), 1000);
    }
  }

  // Each second: update the running timers in place; beep once at the end.
  _tickTimers() {
    const timers = this._timers || {};
    const ids = Object.keys(timers);
    if (!ids.length) {
      clearInterval(this._timerTick);
      this._timerTick = null;
      return;
    }
    for (const id of ids) {
      const t = timers[id];
      const left = Math.round((t.start + t.minutes * 60000 - Date.now()) / 1000);
      const el = this.shadowRoot.querySelector(`[data-timer-left="${CSS.escape(id)}"]`);
      if (el) {
        el.textContent = left <= 0 ? "Time's up!" : `⏱ ${clockText(left)}`;
        el.classList.toggle("up", left <= 0);
      }
      if (left <= 0 && !t.done) {
        t.done = true;
        beep();
        const chore = (this._data.chores || []).find((c) => c.id === id);
        this._toast(`Time's up${chore ? ` for ${chore.name}` : ""}!`);
      }
      // Gone an hour after it ran out.
      if (left < -3600) delete timers[id];
    }
  }

  _tomorrowBody(member) {
    const t = this._data.tomorrow;
    if (!t) return null;
    const events = (t.events || []).filter((e) => !member || !e.member || e.member === member.id);
    const eventTiles = events.map((e) => this._eventTile(e, !member)).join("");
    if (t.away) return { body: `<p class="empty">🏖️ Away tomorrow: no chores.</p>`, count: 0 };
    if (member) {
      const chores = (t.chores || {})[member.id] || [];
      if (!chores.length && !events.length) return null;
      const tiles = chores
        .map((c) => `<div class="tile tomorrow">${c.emoji ? `<span class="emoji">${emo(c.emoji)}</span>` : ""}<span class="label">${esc(c.name)}</span>${c.from_time ? `<span class="sub">From ${esc(timeText(c.from_time))}</span>` : ""}<span class="worth">+${pts(c.points)}</span></div>`)
        .join("");
      return { body: `<div class="tiles" data-fit="tomorrow">${tiles}${eventTiles}</div>`, count: chores.length + events.length };
    }
    const people = this._data.members
      .map((m) => [m, ((t.chores || {})[m.id] || []).length])
      .filter(([, n]) => n);
    if (!people.length && !events.length) return null;
    const counts = people
      .map(([m, n]) => `<div class="tile tomorrow" style="--c:${esc(m.color)}"><span class="who">${this._avatar(m, true)}</span><span class="label">${esc(m.name)}</span><span class="sub">${n} ${n === 1 ? "chore" : "chores"}</span></div>`)
      .join("");
    return { body: `<div class="tiles" data-fit="tomorrow">${counts}${eventTiles}</div>`, count: events.length };
  }

  _screenTiles() {
    return (this._data.screen || [])
      .map((x) => {
        const state = this._hass?.states?.[x.entity_id];
        const value = Number(state?.state);
        const known = state && state.state !== "unknown" && state.state !== "unavailable" && !Number.isNaN(value);
        const text = !known ? "No limit right now" : value <= 0 ? "No time left today" : `${Math.round(value)} min left today`;
        return `<div class="tile screen${known && value <= 0 ? " out" : ""}"><span class="emoji">${x.kind === "tv" ? "📺" : "🎵"}</span><span class="label">${esc(x.name)}</span><span class="sub">${esc(text)}</span></div>`;
      })
      .join("");
  }

  _refreshScreen() {
    const box = this.shadowRoot?.querySelector("[data-screen-tiles]");
    if (box) box.innerHTML = this._screenTiles();
  }

  _weatherTile(w) {
    const temp = w.temperature != null ? `${Math.round(Number(w.temperature))}${w.unit || "°"}` : "";
    return `<div class="tile weather"><span class="emoji">${emo(w.emoji)}</span><span class="label">${esc(temp)} · ${esc(w.feel)}</span><span class="sub">${esc(w.text)}</span></div>`;
  }

  async _openStory(memberId) {
    const member = this._memberById(memberId);
    this._sheet = { type: "story", member: memberId, points: member?.points, entries: null };
    this._renderOverlay();
    try {
      const res = await this._ws({ type: `${DOMAIN}/points_story`, member_id: memberId });
      if (this._sheet?.type === "story" && this._sheet.member === memberId) {
        this._sheet.entries = res.entries;
        this._sheet.points = res.points;
        this._renderOverlay();
      }
    } catch (err) {
      this._sheet = null;
      this._renderOverlay();
      this._toast(err?.message || String(err), true);
    }
  }

  async _sendHighFive(from, to, emoji) {
    if (this._busy) return;
    this._busy = true;
    try {
      await this._ws({ type: `${DOMAIN}/high_five`, from_id: from, to_id: to, emoji });
      this._sheet = null;
      this._toast(`${emoji} High five sent to ${this._memberById(to)?.name || "them"}!`);
      await this._load();
    } catch (err) {
      this._toast(err?.message || String(err), true);
    } finally {
      this._busy = false;
      this._renderOverlay();
    }
  }

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
        const icon = c.emoji ? `<span class="emoji">${emo(c.emoji)}</span>` : `<ha-icon class="icon" icon="${esc(v.icon)}"></ha-icon>`;
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
    if (s.type === "trade") {
      const chore = d.chores.find((c) => c.id === s.id);
      const others = d.members.filter((m) => m.id !== s.member);
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Trade a chore">
        <h3>Trade ${esc(chore?.name || "this chore")}?</h3>
        <p class="muted">Whoever takes it does it today instead, once a parent says yes.</p>
        <label class="check"><input type="checkbox" data-trade-week> For the rest of the week (through Sunday), not just today</label>
        <label class="field"><span>Pay them (optional)</span><span><input type="number" min="0" max="${esc(this._memberById(s.member)?.points || 0)}" data-trade-pay value="0" inputmode="numeric" style="width:90px"> of your points, when a parent says yes</span></label>
        <div class="people small-people">${others.map((m) => `<button class="person pick" style="--c:${esc(m.color)}" data-trade-to="${esc(m.id)}">${this._avatar(m, true)}<span class="name">${esc(m.name)}</span></button>`).join("")}
          <button class="person pick" data-trade-to=""><span class="name">Anyone</span></button></div>
        <div class="actions"><button class="big" data-close>Cancel</button></div></div></div>`;
    }
    if (s.type === "cashout") {
      const member = this._memberById(s.member);
      const n = Number(s.points) || 0;
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Cash out">
        <h3>Cash out points</h3>
        <form data-cashout-form>
          <p class="muted">${esc(member?.name || "")} has ${pts(member?.points || 0)} (${esc(money(member?.points || 0, d.money))}). A parent pays it out.</p>
          <label class="field"><span>Points</span><input type="number" name="points" min="1" max="${esc(member?.points || 0)}" value="${esc(s.points)}" data-cashout-points required inputmode="numeric"></label>
          <p class="cash-preview">${n > 0 ? `= ${esc(money(n, d.money))}` : "&nbsp;"}</p>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button>
          <button class="big primary" type="submit" ${this._busy ? "disabled" : ""}>Cash out</button></div>
        </form></div></div>`;
    }
    if (s.type === "link") {
      const link = (d.links || []).find((l) => l.id === s.id);
      if (!link) return "";
      return `<div class="sheet-bg" data-close><div class="sheet link-sheet${link.mobile === false ? "" : " mobile"}" role="dialog" aria-modal="true" aria-label="${esc(link.name)}">
        <div class="link-head"><h3>${emo(link.emoji, "🔗")} ${esc(link.name)}</h3><button class="big" data-close>Close</button></div>
        <iframe src="${esc(link.url)}" title="${esc(link.name)}" referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
        <p class="muted">Blank page? That site doesn't allow showing it here: <a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">open it in a new tab</a>.</p></div></div>`;
    }
    if (s.type === "how") {
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="How to do it">
        <h3>${esc(s.name)}</h3>
        ${s.how ? `<p class="how">${esc(s.how).replace(/\n/g, "<br>")}</p>` : ""}
        ${s.example === null ? `<p class="muted">Loading the photo…</p>` : s.example ? `<img class="photo-full" src="${esc(s.example)}" alt="${esc(s.name)} done right">` : ""}
        <div class="actions"><button class="big" data-say="${esc(`${s.name}. ${s.how}`)}">🔊 Read it to me</button><button class="big" data-close>Got it</button></div></div></div>`;
    }
    if (s.type === "photo") {
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Photo">
        ${s.url === null ? `<p class="muted">Loading…</p>` : s.url ? `<img class="photo-full" src="${esc(s.url)}" alt="Photo of the chore">` : `<p class="muted">That photo is gone: photos are kept for two weeks.</p>`}
        <div class="actions"><button class="big" data-close>Close</button></div></div></div>`;
    }
    if (s.type === "claim") {
      const claim = (d.claims || []).find((c) => c.id === s.id);
      if (!claim) return "";
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Who did this?">
        <h3>Who did ${esc(claim.name)}?</h3><p>+${pts(claim.points)}</p>
        ${this._people(d.members, "data-claim-member", null)}
        <div class="actions"><button class="big" data-close>Cancel</button></div></div></div>`;
    }
    if (s.type === "pic") {
      const tile = (v, words) => `<button type="button" class="pic-tile" data-pic-choose="${esc(v)}" data-pic-words="${esc(words)}" title="${esc(words.split(" ")[0])}">${emo(v)}</button>`;
      return `<div class="sheet-bg" data-close><div class="sheet pic-sheet" role="dialog" aria-modal="true" aria-label="Pick a picture">
        <h3>Pick a picture</h3>
        <input type="search" data-pic-search placeholder="Find an icon: vacuum, dishes, dog…" aria-label="Find an icon">
        <div class="pic-own" hidden><button type="button" class="pic-tile" data-pic-choose=""></button><span class="muted">Use this icon</span></div>
        <h4>Icons</h4><div class="pic-grid">${PICK_ICONS.map(([v, words]) => tile(v, words)).join("")}</div>
        <p class="pic-none muted" hidden>No icon called that. Try another word, or type a full icon name such as mdi:washing-machine.</p>
        <h4 class="pic-emoji-head">Emojis</h4><div class="pic-grid emojis">${PICK_EMOJIS.map((v) => tile(v, "")).join("")}</div>
        <form class="inline" data-pic-form><label class="field grow"><span>Or type any emoji</span><input type="text" name="pic" maxlength="8" placeholder="🧹"></label>
          <button class="btn" type="submit">Use it</button></form>
        <div class="actions"><button class="big" type="button" data-pic-choose="">No picture</button><button class="big" type="button" data-close>Cancel</button></div>
      </div></div>`;
    }
    if (s.type === "didnt_all") {
      const extra = s.ids.reduce((sum, id) => sum + (s.penalties[id] ?? 0), 0);
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="None of these happened">
        <h3>${s.ids.length === 2 ? "Neither chore" : `None of these ${s.ids.length} chores`} happened?</h3>
        <p class="muted">The points for each are taken back, and each one's penalty: the number in its box, or the chore's own, or the family's.${extra ? ` That's ${esc(pts(extra))} more from the boxes alone.` : ""} Say why if you like: they'll see it.</p>
        <div class="chips">${DIDNT_REASONS.map((r) => `<button class="chip" type="button" data-reason="${esc(r)}">${esc(r)}</button>`).join("")}</div>
        <form data-didnt-all-form>
          <label class="field"><span>Why (optional)</span><input type="text" name="reason" maxlength="200" placeholder="Not done"></label>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button>
          <button class="big bad" type="submit">Take the points back</button></div>
        </form></div></div>`;
    }
    if (s.type === "didnt") {
      const member = this._memberById(s.member);
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Didn't happen">
        <h3>${esc(s.title || "This chore")} didn't happen?</h3>
        <p class="muted">${esc(member ? `${member.name}'s` : "Their")} points for it are taken back${s.penalty ? `, and ${esc(pts(s.penalty))} more` : ""}. Say why if you like: ${esc(member?.name || "they")} will see it.</p>
        <div class="chips">${DIDNT_REASONS.map((r) => `<button class="chip" type="button" data-reason="${esc(r)}">${esc(r)}</button>`).join("")}</div>
        <form data-didnt-form>
          <label class="field"><span>Why (optional)</span><input type="text" name="reason" maxlength="200" placeholder="Bed not made"></label>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button>
          <button class="big bad" type="submit">Take the points back</button></div>
        </form></div></div>`;
    }
    if (s.type === "high5") {
      const from = this._memberById(s.from);
      const others = d.members.filter((m) => m.id !== s.from);
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="High five">
        <h3>A high five from ${esc(from?.name || "you")}</h3>
        <div class="chips five-emoji">${HIGH_FIVES.map((e) => `<button class="chip${s.emoji === e ? " on" : ""}" type="button" data-five-emoji="${esc(e)}" aria-pressed="${s.emoji === e}">${esc(e)}</button>`).join("")}</div>
        <p class="muted">Who for?</p>
        <div class="people small-people">${others.map((m) => `<button class="person pick" style="--c:${esc(m.color)}" data-five-to="${esc(m.id)}" ${this._busy ? "disabled" : ""}>${this._avatar(m, true)}<span class="name">${esc(m.name)}</span></button>`).join("")}</div>
        <div class="actions"><button class="big" data-close>Cancel</button></div></div></div>`;
    }
    if (s.type === "story") {
      const member = this._memberById(s.member);
      const body = s.entries ? (s.entries.length ? this._feed(s.entries, false, true) : `<p class="empty">Nothing yet.</p>`) : `<p class="muted">Loading…</p>`;
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Points story">
        <h3>${esc(member?.name || "")}'s points: ${esc(s.points ?? member?.points ?? 0)}</h3>
        <p class="muted">What earned and spent them lately, with the points before → after.</p>
        <div class="story">${body}</div>
        <div class="actions"><button class="big" data-close>Close</button></div></div></div>`;
    }
    if (s.type === "who") {
      const quest = s.what === "quest" ? (d.quests || []).find((q) => q.id === s.id) : null;
      const pet = s.what === "pet" ? (d.pets || []).find((p) => p.id === s.id) : null;
      const trade = s.what === "trade" ? (d.trades || []).find((t) => t.id === s.id) : null;
      const allowed = (quest || pet)?.members;
      const people = d.members.filter((m) => (!allowed || allowed.includes(m.id)) && (!trade || m.id !== trade.from));
      const what = trade ? `${trade.chore} from ${trade.from_name}` : quest ? `${quest.steps[quest.next]?.name || ""} (${quest.name})` : pet ? `${pet.task} ${pet.name}` : "";
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Who did it">
        <h3>${trade ? "Who's taking it?" : "Who did it?"}</h3><p class="muted">${esc(what)}</p>
        <div class="people small-people">${people.map((m) => `<button class="person pick" style="--c:${esc(m.color)}" data-who-did="${esc(m.id)}">${this._avatar(m, true)}<span class="name">${esc(m.name)}</span></button>`).join("")}</div>
        <div class="actions"><button class="big" data-close>Cancel</button></div></div></div>`;
    }
    if (s.type === "statement") {
      const st = s.statement;
      return `<div class="sheet-bg" data-close><div class="sheet wide" role="dialog" aria-modal="true" aria-label="Statement">
        ${st ? this._statementBody(st) : `<p class="muted">Loading…</p>`}
        <div class="actions"><button class="big" data-close>Close</button>${st ? `<button class="big primary" data-statement-print>Print</button>` : ""}</div></div></div>`;
    }
    if (s.type === "photos") {
      const photos = s.photos;
      const grid = photos === null ? `<p class="muted">Loading…</p>` : photos.length
        ? `<div class="photo-wall">${photos.map((p) => `<figure>${s.urls[p.entry_id] ? `<img src="${esc(s.urls[p.entry_id])}" alt="${esc(p.title)}">` : `<div class="photo-wait">…</div>`}<figcaption>${esc(p.title)}<br><small>${esc(this._memberById(p.member)?.name || "")} · ${esc(new Date(p.at).toLocaleDateString())}</small></figcaption></figure>`).join("")}</div>`
        : `<p class="muted">No chore photos that month.</p>`;
      return `<div class="sheet-bg" data-close><div class="sheet wide" role="dialog" aria-modal="true" aria-label="Photos of the month">
        <h3>📸 Photos of the month</h3>${grid}
        <div class="actions"><button class="big" data-close>Close</button>${photos?.length ? `<button class="big primary" data-photos-print>Print</button>` : ""}</div></div></div>`;
    }
    if (s.type === "bid") {
      const a = (d.auctions || []).find((x) => x.id === s.id);
      const member = this._memberById(s.member);
      const people = d.members.filter((m) => !a?.members || a.members.includes(m.id));
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Bid">
        <h3>${emo(a?.emoji, "🔨")} ${esc(a?.name || "Auction")}</h3>
        <form data-bid-form>
          ${member ? "" : `<label class="field"><span>Who's bidding?</span><select name="member_id" required>${people.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("")}</select></label>`}
          <label class="field"><span>How few points would you do it for? (1 to ${esc(a?.points ?? 1)})</span><input type="number" name="points" min="1" max="${esc(a?.points ?? 1)}" required inputmode="numeric" value="${esc(member ? a?.bids?.[member.id] ?? "" : "")}"></label>
          <p class="muted">${a?.lowest != null ? `The lowest bid so far is ${pts(a.lowest)}.` : "Nobody has bid yet."} The lowest bid when time's up gets the chore; a tie goes to whoever bid first.</p>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button><button class="big primary" type="submit" ${this._busy ? "disabled" : ""}>Bid</button></div>
        </form></div></div>`;
    }
    if (s.type === "reading") {
      const member = this._memberById(s.member);
      const rule = d.reading || {};
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Log reading">
        <h3>📚 What did you read${member ? `, ${esc(member.name)}` : ""}?</h3>
        <form data-reading-form>
          ${member ? "" : `<label class="field"><span>Who read?</span><select name="member_id" required>${d.members.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("")}</select></label>`}
          <label class="field"><span>Minutes</span><input type="number" name="minutes" min="1" max="600" required inputmode="numeric" value="${esc(rule.block_minutes || 20)}"></label>
          <label class="field"><span>Book (optional)</span><input type="text" name="book" maxlength="60"></label>
          <p class="muted">+${pts(rule.points || 0)} for every ${esc(rule.block_minutes || 0)} minutes${rule.max_minutes ? `, up to ${esc(rule.max_minutes)} minutes a day` : ""}. A parent checks it like a chore.</p>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button><button class="big primary" type="submit" ${this._busy ? "disabled" : ""}>Log it</button></div>
        </form></div></div>`;
    }
    if (s.type === "bank") {
      const member = this._memberById(s.member);
      const have = (d.bank || {})[s.member] || 0;
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Use saved TV time">
        <h3>🏦 ${esc(member?.name || "")}'s saved TV time</h3>
        <form data-bank-form>
          <label class="field"><span>How many of your ${have} minutes?</span><input type="number" name="minutes" min="1" max="${have}" required inputmode="numeric" value="${Math.min(have, 30)}"></label>
          <p class="muted">Your TV gets that much more time today.</p>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button><button class="big primary" type="submit" ${this._busy ? "disabled" : ""}>Use them</button></div>
        </form></div></div>`;
    }
    if (s.type === "gifts") {
      const member = this._memberById(s.member);
      const ideas = member?.gift_ideas || [];
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Gift ideas">
        <h3>🎁 ${esc(member?.name || "")}'s gift ideas</h3>
        ${ideas.length ? `<ul class="rows gift-list">${ideas.map((i) => `<li><span class="grow">${esc(i)}</span><button class="btn" data-gift-remove="${esc(i)}" aria-label="Take ${esc(i)} off">✕</button></li>`).join("")}</ul>` : `<p class="muted">Nothing yet. What would you like for your birthday?</p>`}
        <form data-gift-form class="inline"><label class="field grow"><span>Add an idea</span><input type="text" name="text" maxlength="80" required placeholder="A blue bike helmet"></label>
          <button class="big primary" type="submit" style="align-self:end">Add</button></form>
        <p class="muted">A parent can share this list, with your wishlist, with grandparents.</p>
        <div class="actions"><button class="big" data-close>Done</button></div></div></div>`;
    }
    if (s.type === "give") {
      const member = this._memberById(s.member);
      const g = d.give;
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Give points">
        <h3>${emo(g?.emoji, "💝")} Give to ${esc(g?.name || "")}</h3>
        <form data-give-form>
          <label class="field"><span>How many of your ${esc(member?.points ?? 0)} points?</span><input type="number" name="points" min="1" max="${esc(member?.points ?? 0)}" required inputmode="numeric"></label>
          <p class="muted">They come off your points, and go toward ${esc(g?.name || "it")} with everyone else's.</p>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button>
          <button class="big primary" type="submit" ${this._busy ? "disabled" : ""}>Give</button></div>
        </form></div></div>`;
    }
    if (s.type === "race") {
      const others = d.members.filter((m) => m.id !== s.member && m.own_today?.left);
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Race someone">
        <h3>Who do you want to race?</h3>
        <p class="muted">The first of you to finish all of today's own chores gets +${pts(d.challenge_points)}.</p>
        <div class="people small-people">${others.map((m) => `<button class="person pick" style="--c:${esc(m.color)}" data-race-who="${esc(m.id)}">${this._avatar(m, true)}<span class="name">${esc(m.name)}</span></button>`).join("")}</div>
        <div class="actions"><button class="big" data-close>Cancel</button></div></div></div>`;
    }
    if (s.type === "ask" && s.chore) {
      const member = this._memberById(s.member);
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Offer to do a chore">
        <h3>What would you do, ${esc(member?.name || "")}?</h3>
        <form data-ask-form>
          <div class="inline"><label class="field grow"><span>The chore</span><input type="text" name="name" maxlength="60" required placeholder="Wash the car"></label>
          <label class="field"><span>Emoji</span><input type="text" name="emoji" size="3" placeholder="🚗"></label></div>
          <label class="field"><span>How many points do you think it's worth? (optional)</span><input type="number" name="points" min="0" max="10000" inputmode="numeric"></label>
          <p class="muted">A parent says yes (and how many points) or no. A yes puts it in your chores.</p>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button>
          <button class="big primary" type="submit" ${this._busy ? "disabled" : ""}>Offer</button></div>
        </form></div></div>`;
    }
    if (s.type === "ask") {
      const member = this._memberById(s.member);
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Ask for something">
        <h3>What would you like, ${esc(member?.name || "")}?</h3>
        <form data-ask-form>
          <div class="inline"><label class="field grow"><span>What</span><input type="text" name="name" maxlength="60" required placeholder="A sleepover"></label>
          <label class="field"><span>Emoji</span><input type="text" name="emoji" size="3" placeholder="🏕️"></label></div>
          <label class="field"><span>How many points do you think it's worth? (optional)</span><input type="number" name="points" min="0" max="10000" inputmode="numeric"></label>
          <p class="muted">A parent says yes (and how many points it costs) or no. A yes puts it in your rewards.</p>
          <div class="actions"><button class="big" type="button" data-close>Cancel</button>
          <button class="big primary" type="submit" ${this._busy ? "disabled" : ""}>Ask</button></div>
        </form></div></div>`;
    }
    if (s.type === "vote") {
      const vote = d.vote;
      const name = vote?.options?.[s.option] || "";
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Who's voting">
        <h3>Who's voting for ${esc(name)}?</h3>
        <div class="people small-people">${d.members.map((m) => `<button class="person pick" style="--c:${esc(m.color)}" data-vote-who="${esc(m.id)}">${this._avatar(m, true)}<span class="name">${esc(m.name)}</span></button>`).join("")}</div>
        <div class="actions"><button class="big" data-close>Cancel</button></div></div></div>`;
    }
    if (s.type === "report") {
      return `<div class="sheet-bg" data-close><div class="sheet wide" role="dialog" aria-modal="true" aria-label="Weekly report">
        ${s.report ? this._reportBody(s.report) : `<p class="muted">Loading…</p>`}
        <div class="actions"><button class="big" data-close>Close</button>
        <button class="big" data-report-share ${s.report ? "" : "disabled"}>Share</button>
        <button class="big primary" data-report-print ${s.report ? "" : "disabled"}>Print</button></div></div></div>`;
    }
    if (s.type === "pin") {
      const dots = Array.from({ length: Math.max(4, s.pin.length) }, (_v, i) => `<span class="pin-dot${i < s.pin.length ? " on" : ""}"></span>`).join("");
      const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"]
        .map((k) => (k === "" ? "<span></span>" : k === "del"
          ? `<button class="pin-key" data-pin-key="del" aria-label="Delete"><ha-icon icon="mdi:backspace-outline"></ha-icon></button>`
          : `<button class="pin-key" data-pin-key="${k}">${k}</button>`))
        .join("");
      return `<div class="sheet-bg" data-close><div class="sheet pin" role="dialog" aria-modal="true" aria-label="Parent PIN">
        <h3>Parent PIN</h3>
        <div class="pin-dots" aria-label="${s.pin.length} digits">${dots}</div>
        <p class="pin-error" role="alert">${esc(s.error || "")}</p>
        <div class="pin-pad">${keys}</div>
        <div class="actions"><button class="big" data-close>Cancel</button>
        <button class="big primary" data-pin-ok ${s.pin.length < 4 || this._busy ? "disabled" : ""}>Open</button></div>
      </div></div>`;
    }
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
      const photo = chore.photo
        ? `<div class="photo-take">${s.photo ? `<img class="photo-preview" src="${esc(s.photo)}" alt="Your photo">` : ""}
            <label class="big photo-btn">📷 ${s.photo ? "Take another" : "Take a photo"}<input type="file" accept="image/*" capture="environment" data-photo-input hidden></label>
            ${chore.photo === "need" && !s.photo ? `<p class="muted">Take a photo to show it's done.</p>` : ""}</div>`
        : "";
      const blocked = this._busy || (chore.photo === "need" && !s.photo);
      const others = d.members.filter((m) => m.id !== member.id);
      const helpers = others.length
        ? `<p class="muted">Did someone help? They share the points.</p>
          <div class="chips helpers">${others.map((m) => `<button class="chip${(s.helpers || []).includes(m.id) ? " on" : ""}" type="button" data-helper="${esc(m.id)}" aria-pressed="${(s.helpers || []).includes(m.id)}">${esc(m.name)}</button>`).join("")}</div>`
        : "";
      return `<div class="sheet-bg" data-close><div class="sheet" role="dialog" aria-modal="true" aria-label="Chore done">
        <h3>${esc(chore.name)}</h3><p>Done, ${esc(member.name)}? That's +${pts(chore.points)}.</p>
        ${photo}
        ${helpers}
        <div class="actions"><button class="big" data-close>Not yet</button>
        <button class="big primary" data-confirm ${blocked ? "disabled" : ""}>Yes, it's done!</button></div></div></div>`;
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
        <h3>${emo(reward.emoji, "")} ${esc(reward.name)}</h3>
        <p>${esc(member.name)} has ${member.points} of ${pts(reward.points)}: ${reward.points - member.points} more to go.${saving ? "" : " Save up for it?"}</p>
        ${this._bar(member.points, reward.points)}
        <div class="actions" style="margin-top:18px"><button class="big" data-close>Not now</button>
        ${saving ? `<button class="big" data-goal="">Stop saving for it</button>` : `<button class="big primary" data-goal="${esc(reward.id)}" ${this._busy ? "disabled" : ""}>Save for this</button>`}
        <button class="big" data-wish="${esc(reward.id)}">${(member.wishes || []).includes(reward.id) ? "♥ Off my wishlist" : "♡ On my wishlist"}</button>
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
      <h3>${emo(reward.emoji, "")} ${esc(reward.name)}</h3><p>Get it together: ${pts(reward.points)}, shared. A parent says yes first, and until then the points are held.</p>
      ${this._people(people, "data-together", picked)}
      <p class="split${ready ? " ready" : ""}">${line}</p>
      <div class="actions"><button class="big" data-close>Cancel</button>
      <button class="big primary" data-confirm ${ready && !this._busy ? "" : "disabled"}>Ask a parent</button></div></div></div>`;
  }

  // Parents ---------------------------------------------------------------------

  _renderParents() {
    const d = this._data;
    const checks = (d.to_check?.length || 0) + (d.to_give?.length || 0) + (d.to_approve?.length || 0) + (d.trades || []).filter((t) => t.status === "taken").length;
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
      history: () => this._renderHistory(),
    }[this._tab]();
    return bar + body;
  }

  // One-tap points for how someone's doing ("Kind to a sibling" +2,
  // "Not listening" -1). The buttons are the parents' own; each tap is a
  // points change in History, like Change points.
  _gradesCard() {
    const grades = Object.entries(this._data.grade_points || {});
    if (!grades.length || !this._data.members.length) return "";
    return `<div class="card"><h2>Grades</h2>
      <p class="muted">A report card or a test: pick the grade and its points are given straight away. Set the grades and points under <b>Family</b>.</p>
      <form class="edit inline" data-grade-form>
        <label class="field"><span>Who</span><select name="member_id">${this._data.members.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("")}</select></label>
        <label class="field grow"><span>Subject (optional)</span><input type="text" name="subject" maxlength="40" placeholder="Math test"></label>
        <label class="field"><span>Grade</span><select name="grade">${grades.map(([g, p]) => `<option value="${esc(g)}">${esc(g)} (+${p})</option>`).join("")}</select></label>
        <button class="btn primary" type="submit" style="align-self:end">Give the points</button></form></div>`;
  }

  _quickCard() {
    const d = this._data;
    const buttons = d.settings?.quick_points || [];
    if (this._edit?.collection === "quick_points") return `<div class="card"><h2>Quick points</h2>${this._quickForm(buttons)}</div>`;
    const forMember = (m) => buttons.map((b, i) => [b, i]).filter(([b]) => b.members == null || b.members.includes(m.id));
    const people = d.members.filter((m) => forMember(m).length);
    const rows = buttons.length && people.length
      ? `<ul class="rows quick">${people
          .map((m) => `<li>${this._avatar(m, true)}<span class="grow"><b>${esc(m.name)}</b><small>${pts(m.points)}</small></span>
            <span class="quick-buttons">${forMember(m)
              .map(([b, i]) => `<button class="btn ${b.points > 0 ? "good" : "bad"}" data-quick="${i}" data-member-id="${esc(m.id)}" ${this._busy ? "disabled" : ""}>${b.emoji ? `${emo(b.emoji)} ` : ""}${esc(b.label)} ${b.points > 0 ? "+" : "−"}${Math.abs(b.points)}</button>`)
              .join("")}</span></li>`)
          .join("")}</ul>`
      : `<p class="empty">${buttons.length && d.members.length ? "None of the buttons is for anyone yet. Change the buttons to pick who each is for." : d.members.length ? "No buttons yet. Add a few for the things you want to notice, good and not so good." : "Add your family first."}</p>`;
    return `<div class="card"><h2>Quick points</h2>
      <p class="muted">One tap gives or takes points straight away. It shows in History.</p>
      ${rows}<button class="btn" data-new="quick_points">${buttons.length ? "Change the buttons" : "Add buttons"}</button></div>`;
  }

  _quickForm(buttons) {
    const rows = [...buttons, { label: "", emoji: "", points: "" }, { label: "", emoji: "", points: "" }];
    const family = (this._data.members || []).length > 1;
    return `<form class="edit" data-quick-form>
      <p class="muted">Use a minus for points taken away, like −1. Leave a row empty to remove it. Up to 12 buttons.${family ? " Each button is for everyone unless you untick people: it then shows only for whoever is still ticked." : ""}</p>
      <ul class="rows quick-edit">${rows
        .map((b, i) => `<li>${this._pic(`name="emoji" data-quick-row="${i}"`, b.emoji, "+", "Picture")}
          <input type="text" class="grow" name="label" maxlength="40" value="${esc(b.label || "")}" placeholder="Kind to a sibling" aria-label="What it's for">
          <input type="number" name="points" min="-10000" max="10000" value="${esc(b.points)}" placeholder="2" aria-label="Points" style="width:90px">${family ? `<span class="quick-who">${this._whoDropdown(b.members, { id: `quick-who-${i}`, label: "Who it's for", everyone: true })}</span>` : ""}</li>`)
        .join("")}</ul>
      <div class="form-actions"><button class="btn primary" type="submit">Save</button><button class="btn" type="button" data-cancel>Cancel</button></div></form>`;
  }

  // The penalties typed in the chores' boxes (empty boxes left out).
  _penaltyBoxes(ids) {
    const out = {};
    for (const id of ids) {
      const box = this.shadowRoot.querySelector(`[data-penalty-for="${CSS.escape(id)}"]`);
      if (box && box.value.trim() !== "") out[id] = Math.max(0, Math.round(Number(box.value) || 0));
    }
    return out;
  }

  _renderReview() {
    const d = this._data;
    const all = d.to_check.length > 1
      ? `<div class="check-all"><span class="grow">${d.to_check.length === 2 ? "Both chores" : `All ${d.to_check.length} chores`}:</span>
          <button class="btn good" data-review-all="1">Done right</button>
          <button class="btn bad" data-review-all="0">Didn't happen</button></div>`
      : "";
    const check = d.to_check.length
      ? `${all}<ul class="rows">${d.to_check
          .map((e) => {
            const m = this._memberById(e.member);
            return `<li>${m ? this._avatar(m, true) : ""}<span class="grow">${esc(m?.name || "Someone")}: <b>${esc(e.title)}</b><small>${esc(whenText(e.at))} · +${pts(e.points)} given</small></span>
              ${e.photo ? `<button class="btn" data-photo-view="${esc(e.id)}">📷 Photo</button>` : ""}
              <button class="btn good" data-review="${esc(e.id)}" data-approved="1">Done right</button>
              <span class="penalty"><input type="number" min="0" max="10000" data-penalty-for="${esc(e.id)}" placeholder="${esc(e.penalty ?? d.settings?.penalty ?? 0)}" aria-label="Extra points to take if it didn't happen">
              <button class="btn bad" data-didnt="${esc(e.id)}">Didn't happen</button></span></li>`;
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
    const owed = Object.entries(d.owed || {}).filter(([, money]) => money > 0);
    const owedRows = owed.length
      ? `<ul class="rows owed">${owed.map(([id, money]) => {
          const m = this._memberById(id);
          return `<li>${m ? this._avatar(m, true) : ""}<span class="grow">${esc(m?.name || "Someone")} is owed <b>${esc(`${d.money?.currency || ""}${money.toFixed(2)}`)}</b><small>Cash outs not paid yet, added up</small></span>
            <button class="btn primary" data-paid-all="${esc(id)}">Paid it all</button></li>`;
        }).join("")}</ul>`
      : "";
    const give = d.to_give.length
      ? `${owedRows}<ul class="rows">${d.to_give
          .map((e) => {
            const people = (e.together || [e.member]).map((id) => this._memberById(id)).filter(Boolean);
            const who = people.length ? namesText(people.map((m) => m.name)) : "Someone";
            const cash = e.kind === "cashout";
            return `<li><span class="avatars">${people.map((m) => this._avatar(m, true)).join("")}</span><span class="grow">${esc(who)}: <b>${esc(e.title)}</b><small>${esc(whenText(e.at))}${cash ? ` · ${pts(-e.points)}` : ""}</small></span>
              <button class="btn primary" data-given="${esc(e.id)}">${cash ? "Paid" : "Handed out"}</button>${cash ? `<button class="btn bad" data-cash-cancel="${esc(e.id)}">Cancel</button>` : ""}</li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No rewards to hand out.</p>`;
    const taken = (d.trades || []).filter((t) => t.status === "taken");
    const trades = taken.length
      ? `<div class="card"><h2>Trades to say yes to</h2>
        <p class="muted"><b>Yes</b>: whoever took it does the chore today instead. <b>No</b>: it stays with who had it.</p>
        <ul class="rows">${taken
          .map((t) => {
            const taker = this._memberById(t.to);
            return `<li>${taker ? this._avatar(taker, true) : ""}<span class="grow">${esc(taker?.name || "Someone")} takes ${esc(t.from_name)}'s <b>${esc(t.chore)}</b><small>Today · +${pts(t.points)}</small></span>
              <button class="btn good" data-trade-decide="${esc(t.id)}" data-yes="1">Yes</button>
              <button class="btn bad" data-trade-decide="${esc(t.id)}" data-yes="0">No</button></li>`;
          })
          .join("")}</ul></div>`
      : "";
    const auto = d.settings?.auto_check || "";
    return `${this._quickCard()}${this._gradesCard()}${this._requestsCard()}${this._ideasCard()}${approve}${trades}<div class="card"><h2>Chores to check</h2>
        <p class="muted">Points are given as soon as a chore is marked done. <b>Didn't happen</b> takes them back${d.todo_lists.length ? " and puts a to-do item back on its list" : ""}, and takes the penalty in the box next to it: the chore's own penalty, or the family's. Type a number to change it this time.</p>${check}
        <form class="inline penalty-setting" data-penalty-setting>
          <label class="field"><span>When a chore didn't happen, also take away</span>
            <span><input type="number" name="penalty" min="0" max="10000" value="${esc(d.settings?.penalty ?? 0)}" style="width:100px"> points <small>(0: just take back its points)</small></span></label>
          <button class="btn" type="submit">Save</button></form>
        <label class="field" style="margin-top:16px"><span>Count chores nobody checked as done right</span>
          <select data-auto-check>${AUTO_CHECKS.map((a) => `<option value="${a.id}" ${auto === a.id ? "selected" : ""}>${a.label}</option>`).join("")}</select>
          <small>You can still mark one <b>Didn't happen</b> from History.</small></label></div>
      <div class="card"><h2>Rewards and cash outs to hand out</h2>${give}</div>
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
        <div class="field"><span>Live Activities of today's chores</span>
          <label class="check"><input type="checkbox" name="live_activity" ${st.live_activity ? "checked" : ""}> One for the family: how far each child is, on one line</label>
          <label class="check"><input type="checkbox" name="live_per_child" ${st.live_per_child ? "checked" : ""}> One for each child: their own progress, gone once they're all done</label>
          <label class="field"><span>Show from</span><input type="time" name="live_from" value="${esc(st.live_from || "")}" style="max-width:160px"></label>
          <small>Only children with chores of their own today, not parents. Empty: from midnight. On iPhone a Live Activity ends after 8 hours, so start it when the kids get up, such as 6:30 AM.</small></div>
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
            return `<li><span class="grow">${r.emoji ? `${emo(r.emoji)} ` : ""}<b>${esc(r.name)}</b>${r.enabled === false ? " <small>(hidden)</small>" : ""}
              <small>${r.steps.length} ${r.steps.length === 1 ? "step" : "steps"} · +${pts(r.points)} when finished · ${esc(who.length ? namesText(who) : "Everyone")} · ${esc(when)}</small></span>
              <button class="btn" data-move="routines" data-id="${esc(r.id)}" data-offset="-1" ${i === 0 ? "disabled" : ""} aria-label="Move up">↑</button>
              <button class="btn" data-move="routines" data-id="${esc(r.id)}" data-offset="1" ${i === last ? "disabled" : ""} aria-label="Move down">↓</button>
              <button class="btn" data-edit="routines" data-id="${esc(r.id)}">Edit</button>
              <button class="btn bad" data-delete="routines" data-id="${esc(r.id)}">Remove</button></li>${this._inline("routines", r.id)}`;
          })
          .join("")}</ul>`
      : `<p class="empty">No routines yet. A morning or bedtime checklist is a good start.</p>`;
    const form = edit?.collection === "routines" && !edit.item?.id ? this._routineForm(edit.item) : `<button class="btn primary" data-new="routines">Add a routine</button>`;
    return `<div class="card"><h2>Routines</h2>
      <p class="muted">A checklist someone works through on the Family dashboard, one step at a time. Ticking the last step finishes it: the points are given straight away and it waits under <b>To check</b>, like a chore. Ticked steps start fresh each day.</p>
      ${rows}${form}</div>`;
  }

  // The form for the item being edited, opened right under its row, so the
  // rows after it move down until it's saved or cancelled.
  _inline(collection, id) {
    const edit = this._edit;
    if (edit?.collection !== collection || !id || edit.item?.id !== id) return "";
    const form = { routines: "_routineForm", chores: "_choreForm", todo_lists: "_listForm", rewards: "_rewardForm", controls: "_controlForm", members: "_memberForm" }[collection];
    return `<li class="edit-row">${this[form](edit.item)}</li>`;
  }

  // A pool chore's pick this week, and Put back for a parent.
  _poolStatus(c) {
    if (!c.pool) return "";
    const row = (this._data.picks?.pool || []).find((p) => p.id === c.id);
    const who = row?.picked_by ? this._memberById(row.picked_by) : null;
    return who
      ? `<span class="pill">Picked by ${esc(who.name)}</span><button class="btn" data-unpick="${esc(c.id)}">Put back</button>`
      : `<span class="pill">In the pool</span>`;
  }

  _routineForm(item) {
    const r = item || { name: "", points: 5, members: [], steps: [], enabled: true };
    return `<form class="edit" data-form="routines" data-id="${esc(r.id || "")}">
      <div class="inline">
        <label class="field"><span>Routine</span><input type="text" name="name" value="${esc(r.name)}" required placeholder="Morning"></label>
        ${this._picField(r.emoji, "🌅")}
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
      <label class="check"><input type="checkbox" name="beat_clock" ${r.beat_clock ? "checked" : ""}> Beat the clock: +${pts(this._data.settings?.beat_clock_points || 0)} for finishing before it's time to leave <small>(set the points and times under Family)</small></label>
      <label class="check"><input type="checkbox" name="enabled" ${r.enabled !== false ? "checked" : ""}> Show it on the Family dashboard</label>
      <div class="form-actions"><button class="btn primary" type="submit">Save routine</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  _renderChores() {
    const d = this._data;
    const edit = this._edit;
    const chores = d.all_chores.length
      ? `<ul class="rows">${d.all_chores
          .map((c) => `<li><span class="grow">${c.emoji ? `${emo(c.emoji)} ` : ""}<b>${esc(c.name)}</b>${c.enabled ? "" : " (off)"}
              <small>+${pts(c.points)} · ${esc(repeatText(c))}${whenShown(c) ? ` · ${esc(whenShown(c))}` : ""}${c.from_date ? ` · ${esc(monthDayText(c.from_date))} to ${esc(monthDayText(c.until_date))}` : ""} · ${esc(c.turns ? `Turns: ${this._whoText(c.members)}` : c.grab || !c.members?.length ? `Up for grabs: ${this._whoText(c.members)}` : `Their own: ${this._whoText(c.members)}`)}${c.todo_list ? ` · on ${esc(this._listName(c.todo_list))}` : ""}</small></span>
              ${this._poolStatus(c)}
              <button class="btn" data-edit="chores" data-id="${esc(c.id)}">Edit</button>
              <button class="btn bad" data-delete="chores" data-id="${esc(c.id)}">Delete</button></li>${this._inline("chores", c.id)}`)
          .join("")}</ul>`
      : `<p class="empty">No chores added here yet.</p>`;
    const choreForm = edit?.collection === "chores" && !edit.item?.id ? this._choreForm(edit.item) : `<button class="btn primary" data-new="chores">Add a chore</button>`;
    const lists = d.todo_lists.length
      ? `<ul class="rows">${d.todo_lists
          .map((t) => {
            const own = (t.items || []).filter((i) => i.rated).length;
            return `<li><span class="grow"><b>${esc(t.name)}</b><small>+${pts(t.points)} each unless the item says otherwise${own ? ` · ${own} with their own points` : ""} · ${esc(t.grab || !t.members?.length ? `Up for grabs: ${this._whoText(t.members)}` : `Their own: ${this._whoText(t.members)}`)}${t.due_only ? " · only when due" : ""}</small></span>
              <button class="btn" data-edit="todo_lists" data-id="${esc(t.id)}">Points for items</button>
              <button class="btn" data-edit="todo_lists" data-id="${esc(t.id)}">Edit</button>
              <button class="btn bad" data-delete="todo_lists" data-id="${esc(t.id)}">Remove</button></li>${this._inline("todo_lists", t.id)}`;
          })
          .join("")}</ul>`
      : `<p class="empty">No to-do lists yet.</p>`;
    const listForm = edit?.collection === "todo_lists" && !edit.item?.id ? this._listForm(edit.item) : `<button class="btn primary" data-new="todo_lists">Add a to-do list</button>`;
    return `${this._boostCard()}${this._choreMatrix()}<div class="card"><h2>Chores</h2>${chores}${choreForm}</div>${this._pickCard()}${this._auctionsCard()}${this._questsCard()}${this._petsCard()}
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
            return `<tr><th class="chore">${c.emoji ? `${emo(c.emoji)} ` : ""}${esc(c.name)}<small>${esc(when)}</small></th>${people.map((m) => `<td>${mark[key](c, m)}</td>`).join("")}</tr>`;
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
        ${this._picField(c.emoji, "🛏️")}
        <label class="field"><span>Points</span><input type="number" name="points" min="0" max="10000" value="${esc(c.points)}"></label>
        <label class="field"><span>Penalty if it didn't happen</span><input type="number" name="penalty" min="0" max="10000" value="${esc(c.penalty ?? "")}" placeholder="Family's (${esc(this._data.settings?.penalty ?? 0)})"></label>
        <label class="field"><span>Comes back</span><select name="repeat" data-repeat>${REPEATS.map((r) => `<option value="${r.id}" ${r.id === c.repeat ? "selected" : ""}>${r.label}</option>`).join("")}</select></label>
        <label class="field" data-days-field ${c.repeat === "after_days" ? "" : "hidden"}><span>Days after it's done</span><input type="number" name="repeat_days" min="1" max="365" value="${esc(c.repeat_days || 3)}"></label>
        ${this._data.members.some((m) => m.birthday && m.birth_year) || c.min_age != null || c.max_age != null ? `<label class="field"><span>Youngest age</span><input type="number" name="min_age" min="0" max="120" value="${esc(c.min_age ?? "")}" placeholder="Any" style="width:80px"></label>
        <label class="field"><span>Oldest age</span><input type="number" name="max_age" min="0" max="120" value="${esc(c.max_age ?? "")}" placeholder="Any" style="width:80px"></label>` : ""}
        <label class="field"><span>Timer (minutes, 0: none)</span><input type="number" name="timer_minutes" min="0" max="180" value="${esc(c.timer_minutes || 0)}" style="width:90px"></label>
        <label class="field"><span>Bonus for beating it</span><input type="number" name="timer_bonus" min="0" max="10000" value="${esc(c.timer_bonus || 0)}" style="width:90px"></label>
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
      <div class="field"><span>Season</span><div class="inline">
        ${this._monthDay("from", c.from_date, "From")} ${this._monthDay("until", c.until_date, "until")}</div>
        <small>Only between these days, every year (they can wrap past New Year: December to March). Empty: all year. Rake leaves in the fall, shovel the walk in the winter.</small></div>
      ${this._remindField(c)}
      <label class="field"><span>How to do it (optional)</span><textarea name="how" rows="3" maxlength="1000" placeholder="Pillow at the top, blanket pulled straight, toys in the box">${esc(c.how || "")}</textarea>
        <small>Shown when someone taps ⓘ on the chore.</small></label>
      ${c.id ? `<div class="field"><span>Photo of it done right</span><span class="inline">
        <label class="btn photo-btn">📷 ${c.example ? "Change the photo" : "Add a photo"}<input type="file" accept="image/*" data-example-input="${esc(c.id)}" hidden></label>
        ${c.example ? `<button class="btn" type="button" data-example-remove="${esc(c.id)}">Remove the photo</button>` : ""}</span>
        <small>Shown with the instructions, so everyone knows what done looks like.</small></div>` : ""}
      ${this._choreExtras(c)}
      <div class="field"><span>Who can do it</span>${this._whoChecks(c.members)}</div>
      ${this._grabField(c.grab, c.team)}
      <label class="check"><input type="checkbox" name="turns" data-turns ${c.turns ? "checked" : ""}> They take turns (tick two or more people above)</label>
      <div class="inline" data-turn-fields ${c.turns ? "" : "hidden"}>
        <label class="field"><span>The turn moves on</span><select name="turn_every">${TURN_EVERY.map((t) => `<option value="${t.id}" ${(c.turn_every || "time") === t.id ? "selected" : ""}>${t.label}</option>`).join("")}</select></label>
        <label class="field"><span>Whose turn is it now?</span><select name="turn_first">${this._data.members.map((m) => `<option value="${esc(m.id)}" ${this._currentTurn(c) === m.id ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select></label>
      </div>
      <label class="check"><input type="checkbox" name="enabled" ${c.enabled ? "checked" : ""}> Show it on the Family dashboard</label>
      <div class="form-actions"><button class="btn primary" type="submit">Save chore</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  // A photo when it's done, a streak bonus, the weekly pool, and a device
  // that finishes it.
  _choreExtras(c) {
    const finishers = this._choices?.finishers || [];
    const done = c.done_when || {};
    return `<div class="inline">
        <label class="field"><span>How hard</span><select name="difficulty">
          <option value="" ${c.difficulty ? "" : "selected"}>Not set</option>
          <option value="easy" ${c.difficulty === "easy" ? "selected" : ""}>⭐ Easy</option>
          <option value="medium" ${c.difficulty === "medium" ? "selected" : ""}>⭐⭐ Medium</option>
          <option value="hard" ${c.difficulty === "hard" ? "selected" : ""}>⭐⭐⭐ Hard</option></select></label>
        <label class="field"><span>Photo when it's done</span><select name="photo">
          <option value="" ${c.photo ? "" : "selected"}>No photo</option>
          <option value="ask" ${c.photo === "ask" ? "selected" : ""}>Ask for one (they can skip it)</option>
          <option value="need" ${c.photo === "need" ? "selected" : ""}>Needs one</option></select></label>
        <label class="field"><span>Bonus every … days in a row</span><input type="number" name="streak_days" min="0" max="60" value="${esc(c.streak_days || 0)}" style="width:110px"></label>
        <label class="field"><span>Streak bonus points</span><input type="number" name="streak_bonus" min="0" max="10000" value="${esc(c.streak_bonus || 0)}" style="width:110px"></label>
      </div>
      <small>A photo shows under <b>To check</b>. The streak counts days (weeks, for a weekly chore) the same person did it in a row; 0: no streak bonus.</small>
      <label class="check"><input type="checkbox" name="pool" ${c.pool ? "checked" : ""}> In the pick-your-chores pool: nobody's until someone picks it for the week</label>
      <div class="inline">
        <label class="field grow"><span>Done when this device…</span><input type="text" name="done_entity" list="family-finishers" value="${esc(done.entity_id || "")}" placeholder="Search: robot vacuum, dishwasher door…" autocomplete="off"></label>
        <label class="field"><span>…changes to</span><input type="text" name="done_state" list="family-finisher-states" value="${esc(done.state || "")}" placeholder="docked" style="width:140px"></label>
      </div>
      <datalist id="family-finishers">${finishers.map((f) => `<option value="${esc(f.entity_id)}">${esc(f.name)}</option>`).join("")}</datalist>
      <datalist id="family-finisher-states">${["docked", "returning", "idle", "on", "off", "open", "closed"].map((x) => `<option value="${x}"></option>`).join("")}</datalist>
      <small>Optional. Whoever started the device from Home Assistant gets the points; if that's not known, the Family dashboard asks <b>Who did this?</b></small>
      <div class="inline">
        <label class="field grow"><span>Only when this…</span><input type="text" name="only_entity" list="family-watchables" value="${esc(c.only_when?.entity_id || "")}" placeholder="Search: Kind of day, house mode…" autocomplete="off"></label>
        <label class="field"><span>…shows</span><input type="text" name="only_states" value="${esc((c.only_when?.states || []).join(", "))}" placeholder="School day" style="width:180px"></label>
      </div>
      <datalist id="family-watchables">${(this._choices?.watchables || []).map((w) => `<option value="${esc(w.entity_id)}">${esc(w.name)} (now: ${esc(w.state)})</option>`).join("")}</datalist>
      <small>Optional. The chore shows only while this shows one of these (separate them with commas), such as Daily Routine's <b>Kind of day</b> being School day.</small>
      <label class="field"><span>When it's done, also start</span><select name="on_done"><option value="">Nothing</option>${(this._choices?.starters || []).map((x) => `<option value="${esc(x.entity_id)}" ${x.entity_id === c.on_done ? "selected" : ""}>${esc(x.name)}</option>`).join("")}${c.on_done && !(this._choices?.starters || []).some((x) => x.entity_id === c.on_done) ? `<option value="${esc(c.on_done)}" selected>${esc(c.on_done)}</option>` : ""}</select>
        <small>A script, scene or button, such as one that gives TV time or turns the desk lamp off once homework is done.</small></label>`;
  }

  // Their own chore, or up for grabs among the people ticked.
  _grabField(grab, team = null) {
    const teamOption = team === null ? "" : `<option value="team" ${team ? "selected" : ""}>Team chore: each one ticks it, and the points count once they all have</option>`;
    return `<label class="field"><span>How it's done</span><select name="grab">
      <option value="" ${grab || team ? "" : "selected"}>Their own chore: each one ticked does it</option>
      <option value="1" ${grab ? "selected" : ""}>Up for grabs: whoever's first, for extra points</option>${teamOption}</select>
      <small>Their own chores count for the all-done bonus and streaks; up for grabs is extra. Nobody ticked: up for grabs for everyone. Taking turns is always their own chore.${team === null ? "" : " A team chore needs two or more people ticked."}</small></label>`;
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
    // Picked speakers first; the list folds away, as a home can have dozens.
    const sorted = [...players].sort((a, b) => Number(picked.has(b.entity_id)) - Number(picked.has(a.entity_id)));
    const names = sorted.filter((p) => picked.has(p.entity_id)).map((p) => p.name);
    const boxes = players.length
      ? `<details class="speakers"><summary>Speakers: <b>${esc(names.length ? namesText(names) : "none picked")}</b></summary>
          ${players.length > 8 ? `<input type="search" class="speaker-find" data-speaker-find placeholder="Find a speaker" aria-label="Find a speaker">` : ""}
          <div class="inline">${sorted.map((p) => `<label class="check" data-speaker-name="${esc(p.name.toLowerCase())}"><input type="checkbox" name="remind_speakers" value="${esc(p.entity_id)}" ${picked.has(p.entity_id) ? "checked" : ""}> ${esc(p.name)}</label>`).join("")}</div></details>`
      : `<small>No speakers in Home Assistant yet.</small>`;
    return `<div class="field"><span>Say it on a speaker</span>
      <label class="field"><span>At</span><input type="time" name="remind_time" value="${esc(c.remind_time || "")}" style="max-width:160px"></label>
      ${boxes}
      <small>${voice ? "At this time, on its days, the speakers say who still has it to do. Nothing is said once it's done." : "Pick a voice first under <b>Family</b> → <b>Speaker reminders</b>."}</small></div>`;
  }

  _itemPoints(list) {
    const items = list.items || [];
    const row = (i) => `<li class="${i.skip ? "skipped" : ""}">${this._pic(`data-item-emoji="${esc(i.name)}"`, i.emoji, "+", `Picture for ${i.name}`)}<span class="item-name">${esc(i.name)}</span>
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
    const goals = this._data.family_goals || [];
    const editing = this._goalEdit;
    const rows = goals.map((g) => `<li class="goal-status"><span class="grow">${emo(g.emoji, "🏆")} <b>${esc(g.name)}</b>${this._bar(g.progress, g.target)}
        <small>${g.kids ? "Just the kids · " : g.members ? `${esc(namesText(g.members.map((id) => this._memberById(id)?.name).filter(Boolean)))} · ` : ""}${g.reached ? "Reached! Hand it out, then start it again or remove it." : `${g.progress} of ${g.target} points together since ${esc(whenText(g.since))}`}</small></span>
        <button class="btn" data-goal-edit="${esc(g.id)}">${g.reached ? "Start again" : "Change"}</button><button class="btn bad" data-goal-remove="${esc(g.id)}">Remove</button></li>`).join("");
    const g = editing === "new" ? {} : goals.find((x) => x.id === editing);
    const form = g
      ? `<form class="edit" data-goal-form>
          <input type="hidden" name="id" value="${esc(g.id || "")}">
          <div class="inline">
            ${this._picField(g.emoji, "🍕")}
            <label class="field grow"><span>What it's for</span><input type="text" name="name" maxlength="60" required value="${esc(g.name || "")}" placeholder="Pizza night"></label>
            <label class="field"><span>Points together</span><input type="number" name="target" min="1" max="10000" required value="${esc(g.target || "")}" placeholder="200" style="width:110px"></label>
          </div>
          <label class="field"><span>Who it's for</span><select name="who" data-goal-who>
            <option value="all" ${!g.kids && !g.members ? "selected" : ""}>The whole family</option>
            <option value="kids" ${g.kids ? "selected" : ""}>Just the kids</option>
            <option value="some" ${g.members ? "selected" : ""}>Some of us</option></select>
            <small>Just the kids: only their points count, and it doesn't show on the parents' own pages.</small></label>
          <div class="field goal-people" ${g.members ? "" : "hidden"}><span>Who</span>${this._whoChecks(g.members || []).replace("None ticked: anyone can do it.", "Tick two or more.")}</div>
          ${g.id ? `<label class="check"><input type="checkbox" name="restart" ${g.reached ? "checked" : ""}> Start counting again from now</label>` : ""}
          <div class="form-actions"><button class="btn primary" type="submit">Save goal</button><button class="btn" type="button" data-goal-edit="">Cancel</button></div></form>`
      : goals.length < 6 ? `<div class="form-actions"><button class="btn primary" data-goal-edit="new">${goals.length ? "Add another goal" : "Set a family goal"}</button></div>` : "";
    return `<div class="card"><h2>Family goals</h2>
      <p class="muted">Things to work toward together, up to six at a time: for the whole family, just the kids, or some of you. Points from their chores count toward each one; nobody spends any.</p>
      ${rows ? `<ul class="rows">${rows}</ul>` : `<p class="empty">No family goal right now.</p>`}${form}</div>`;
  }

  _auctionsCard() {
    const auctions = (this._data.auctions || []).filter((a) => a.status === "open");
    const rows = auctions.map((a) => {
      const bids = Object.entries(a.bids || {}).sort((x, y) => x[1] - y[1]).map(([id, p]) => `${this._memberById(id)?.name || "?"} ${p}`).join(", ");
      return `<li><span class="grow">${emo(a.emoji, "🔨")} <b>${esc(a.name)}</b><small>Up to ${pts(a.points)} · closes ${esc(whenText(a.closes))}${bids ? ` · bids: ${esc(bids)}` : " · no bids yet"}</small></span>
        <button class="btn primary" data-auction-close="${esc(a.id)}">Close now</button><button class="btn bad" data-auction-cancel="${esc(a.id)}">Cancel</button></li>`;
    }).join("");
    return `<div class="card"><h2>Chore auctions</h2>
      <p class="muted">Put a bigger job up for auction. The kids bid how few points they'd do it for; when time's up (or you close it) the lowest bid gets it as a one-off chore worth their bid.</p>
      ${rows ? `<ul class="rows">${rows}</ul>` : ""}
      <form class="edit" data-auction-form>
        <div class="inline">${this._picField(null, "🔨")}<label class="field grow"><span>The chore</span><input type="text" name="name" maxlength="60" required placeholder="Clean out the garage"></label>
        <label class="field"><span>Up to (points)</span><input type="number" name="points" min="1" max="10000" required value="20" style="width:100px"></label>
        <label class="field"><span>Bidding for (minutes)</span><input type="number" name="minutes" min="5" max="1440" required value="60" style="width:100px"></label></div>
        <div class="field"><span>Who can bid</span>${this._whoDropdown(null, { id: "auction-who", label: "Who can bid", everyone: true })}</div>
        <div class="form-actions"><button class="btn primary" type="submit">Start the auction</button></div></form></div>`;
  }

  async _shareGifts(memberId) {
    try {
      const { text } = await this._ws({ type: `${DOMAIN}/gifts/text`, member_id: memberId });
      if (navigator.share) {
        try {
          await navigator.share({ text });
          return;
        } catch (_err) {
          // Cancelled, or not allowed here: copy it instead.
        }
      }
      await navigator.clipboard.writeText(text);
      this._toast("Copied. Paste it into a message.");
    } catch (err) {
      this._toast(err?.message || String(err), true);
    }
  }

  _giftsCard() {
    const members = this._data.members;
    if (!members.length) return "";
    const rows = members.map((m) => `<li>${this._avatar(m, true)}<span class="grow"><b>${esc(m.name)}</b><small>${(m.gift_ideas || []).length ? esc((m.gift_ideas || []).join(", ")) : "No gift ideas yet"}${(m.wishes || []).length ? ` · ${m.wishes.length} on their wishlist` : ""}</small></span>
      <button class="btn" data-gift-share="${esc(m.id)}">Share</button></li>`).join("");
    return `<div class="card"><h2>Gift ideas</h2><p class="muted">What the kids added under <b>Gift ideas</b>, plus their wishlist. <b>Share</b> sends the list to grandparents or copies it.</p><ul class="rows">${rows}</ul></div>`;
  }

  _renderRewards() {
    const d = this._data;
    const edit = this._edit;
    const rows = d.rewards.length
      ? `<ul class="rows">${d.rewards
          .map((r) => `<li><span class="grow">${r.emoji ? `${emo(r.emoji)} ` : ""}<b>${esc(r.name)}</b>
              <small>${this._rewardLine(r)}</small></span>
              <button class="btn" data-edit="rewards" data-id="${esc(r.id)}">Edit</button>
              <button class="btn bad" data-delete="rewards" data-id="${esc(r.id)}">Delete</button></li>${this._inline("rewards", r.id)}`)
          .join("")}</ul>`
      : `<p class="empty">No rewards yet.</p>`;
    const form = edit?.collection === "rewards" && !edit.item?.id ? this._rewardForm(edit.item) : `<button class="btn primary" data-new="rewards">Add a reward</button>`;
    const b = d.bonus || {};
    return `${this._familyGoalCard()}${this._mostWantedCard()}${this._giftsCard()}<div class="card"><h2>Rewards</h2>${rows}${form}</div>
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
        ${this._picField(r.emoji, "📺")}
        <label class="field"><span>Costs</span><input type="number" name="points" min="0" max="10000" value="${esc(r.points)}"></label>
        <div class="field"><span>Shop days</span><div class="inline">${DAYS.map((x, i) => `<label class="check"><input type="checkbox" name="shop_days" value="${i}" ${(r.shop_days || []).includes(i) ? "checked" : ""}> ${x}</label>`).join("")}</div>
          <small>None ticked: any day. Tick Saturday so the kids save up all week.</small></div>
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
            const icon = c.emoji ? `${emo(c.emoji)} ` : `<ha-icon icon="${esc(DOMAIN_ICONS[domain] || "mdi:eye")}"></ha-icon> `;
            const asks = c.confirm && c.kind !== "view" ? " · asks first" : "";
            return `<li><span class="grow">${icon}<b>${esc(c.label)}</b>
              <small>${esc(KIND_TEXT[c.kind] || "")} · ${esc(c.members?.length ? `Shown to ${this._whoText(c.members)}` : "Shown to everyone")}${asks}</small></span>
              <button class="btn" data-move="controls" data-id="${esc(c.id)}" data-offset="-1" ${i === 0 ? "disabled" : ""} aria-label="Move up">↑</button>
              <button class="btn" data-move="controls" data-id="${esc(c.id)}" data-offset="1" ${i === last ? "disabled" : ""} aria-label="Move down">↓</button>
              <button class="btn" data-edit="controls" data-id="${esc(c.id)}">Edit</button>
              <button class="btn bad" data-delete="controls" data-id="${esc(c.id)}">Remove</button></li>${this._inline("controls", c.id)}`;
          })
          .join("")}</ul>`
      : `<p class="empty">Nothing yet. Add scenes, lights, blinds or anything else the family should be able to use or see.</p>`;
    const form = edit?.collection === "controls" && !edit.item?.id ? this._controlForm(edit.item) : `<button class="btn primary" data-new="controls">Add to the dashboard</button>`;
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
        ${this._picField(c.emoji, "🎬")}
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
          <label class="field"><span>To buy</span><textarea name="ingredients" rows="2" maxlength="500" placeholder="${i ? "" : "Tortillas, cheese, salsa"}">${esc(day.ingredients || "")}</textarea></label>
          <button class="btn" type="submit">Save</button></form>`;
      })
      .join("");
    return `<div class="card"><h2>Meals for the week</h2>
      <p class="muted">What's for breakfast, lunch and dinner. Today's and tomorrow's show on the Family dashboard. Leave a meal empty to leave it out.</p>
      ${rows}</div>${this._shoppingCard()}${this._voteCard()}`;
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
      </form></div>${this._countdownCard()}${this._calendarAddCard()}`;
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

  _linkRow(l) {
    const people = this._data.members.map((m) => `<option value="${esc(m.id)}" ${l.member === m.id ? "selected" : ""}>${esc(m.name)}</option>`).join("");
    return `<div class="inline link-row" data-link-row="${esc(l.id || "")}">
      ${this._picField(l.emoji, "🍎")}
      <label class="field"><span>Name</span><input name="name" maxlength="40" value="${esc(l.name || "")}" placeholder="School lunch"></label>
      <label class="field grow"><span>Address</span><input name="url" type="url" value="${esc(l.url || "")}" placeholder="https://"></label>
      <label class="field"><span>Whose page</span><select name="member"><option value="">Everyone's</option>${people}</select></label>
      <label class="check" style="align-self:end" title="Shows the site as it looks on a phone"><input type="checkbox" name="mobile" ${l.mobile === false ? "" : "checked"}> Mobile view</label>
      <button class="btn" type="button" data-link-remove style="align-self:end" aria-label="Remove this link">Remove</button></div>`;
  }

  _linksCard() {
    const links = this._data.settings?.links || this._data.links || [];
    return `<div class="card"><h2>Links</h2>
      <p class="muted">Web pages the kids can open from the Family dashboard, like the school lunch menu. Each opens on its own in a window over the dashboard, with no address bar.</p>
      <form class="edit" data-links-form><div data-link-rows>${(links.length ? links : [{}]).map((l) => this._linkRow(l)).join("")}</div>
        <div class="form-actions"><button class="btn" type="button" data-link-add>Add a link</button><button class="btn primary" type="submit">Save</button></div></form></div>`;
  }

  _weatherCard() {
    const weathers = this._choices?.weathers || [];
    const current = this._data.settings?.weather_entity || "";
    const body = weathers.length
      ? `<form class="edit" data-weather-form><div class="inline"><label class="field"><span>Weather</span><select name="weather_entity"><option value="">Off</option>${weathers.map((w) => `<option value="${esc(w.entity_id)}" ${current === w.entity_id ? "selected" : ""}>${esc(w.name)}</option>`).join("")}</select></label>
          <button class="btn" type="submit" style="align-self:end">Save</button></div></form>`
      : `<p class="empty">No weather in Home Assistant yet. Add a weather integration, such as Met.no.</p>`;
    return `<div class="card"><h2>What to wear</h2>
      <p class="muted">Shows today's weather on the Family dashboard in kid terms, like "Cold. Wear a coat and a hat."</p>${body}</div>`;
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

  _holdForm(m) {
    const choice = this._holdChoice || "1";
    return `<form class="edit hold-form" data-hold-form="${esc(m.id)}">
      <p class="muted">${esc(m.name)} can't spend points on rewards or cash out until then. Chores still earn points, and they can still save up.</p>
      <div class="inline">
        <label class="field"><span>For</span><select name="for" data-hold-choice>${HOLD_FOR.map(([v, label]) => `<option value="${v}" ${v === choice ? "selected" : ""}>${label}</option>`).join("")}</select></label>
        ${choice === "until" ? `<label class="field"><span>Through</span><input type="date" name="until" required></label>` : ""}
        <label class="field grow"><span>Why (optional, they'll see it)</span><input type="text" name="reason" maxlength="80"></label>
      </div>
      <div class="form-actions"><button class="btn primary" type="submit">Hold rewards</button><button class="btn" type="button" data-hold-cancel>Cancel</button></div>
    </form>`;
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
              ${m.held_until
                ? `<span class="hold-tag">⏸ Rewards on hold until ${esc(holdText(m.held_until))}${m.hold_reason ? ` · ${esc(m.hold_reason)}` : ""}</span><button class="btn" data-hold-lift="${esc(m.id)}">Lift the hold</button>`
                : `<button class="btn" data-hold-open="${esc(m.id)}">Hold rewards</button>`}
              <button class="btn" data-edit="members" data-id="${esc(m.id)}">Edit</button>
              <button class="btn bad" data-delete="members" data-id="${esc(m.id)}">Remove</button>
              ${this._holdFor === m.id ? this._holdForm(m) : ""}</li>${this._inline("members", m.id)}`)
          .join("")}</ul>`
      : `<p class="empty">No family members yet.</p>`;
    const form = edit?.collection === "members" && !edit.item?.id ? this._memberForm(edit.item) : `<button class="btn primary" data-new="members">Add a family member</button>`;
    return `<div class="card"><h2>Family</h2>
      <p class="muted">Link someone to their Home Assistant person to use its picture. If they log in to Home Assistant, the Family dashboard opens on their own page.</p>
      ${rows}${form}</div>
      ${this._awayCard()}
      ${this._allowanceCard()}
      ${this._savingCard()}
      ${this._giveCard()}
      ${this._extrasCard()}
      ${this._themeCard()}
      ${this._funCard()}
      ${this._leaveCard()}
      ${this._calendarCard()}
      ${this._voiceCard()}
      ${this._weatherCard()}
      ${this._linksCard()}
      ${this._sectionsCard()}
      <div class="card"><h2>Shared screen</h2>
        <p class="muted">Home Assistant only offers dashboards as a login's default, not sidebar pages like this one. Make a dashboard that shows the Family dashboard, then log in on the shared screen and pick <b>${esc(DASHBOARD_TITLE)}</b> under your profile's <b>Dashboard</b>.</p>
        <p class="muted">It has a <b>Home</b> tab for everyone and a tab for each family member, and the tabs follow when you add, rename or remove someone here. You can add your own tabs and cards to it in Home Assistant; they're kept. You can also add the <b>Family</b> card to any dashboard yourself, for everyone or for one person.</p>
        ${this._data.is_admin
          ? `<button class="btn primary" data-make-dashboard ${this._busy ? "disabled" : ""}>${this._hasDashboard ? "Update the Family dashboard" : "Make a Family dashboard"}</button>`
          : `<p class="muted">Making or updating it needs an administrator's login.</p>`}
        <p class="muted"><b>Wall view</b> is for a TV or a tablet on the wall: everyone's points and today's chores, big enough to read across the room. Open the Family page with <code>#wall</code> at the end of its address, or add the Family card with <code>wall: true</code>.</p></div>
      ${this._pinCard()}`;
  }

  _pinCard() {
    const d = this._data;
    const pins = d.pins || {};
    const pinForm = (own, set) => `<form class="inline pin-form" data-pin-form data-own="${own ? 1 : 0}">
        <label class="field"><span>${set ? "New PIN" : "PIN"}</span><input name="pin" type="password" inputmode="numeric" autocomplete="new-password" pattern="[0-9]{4,8}" minlength="4" maxlength="8" required placeholder="4 to 8 digits"></label>
        <button class="btn primary" type="submit" ${this._busy ? "disabled" : ""}>${set ? "Change" : "Set"}</button>
        ${set ? `<button class="btn" type="button" data-pin-clear="${own ? 1 : 0}">Remove</button>` : ""}
      </form>`;
    const body = d.is_admin
      ? `<h3 class="pin-head">Family PIN</h3>
        <p class="muted">${pins.family ? "Set. Any parent can use it." : "Not set."}</p>${pinForm(false, pins.family)}
        <h3 class="pin-head">Your own PIN</h3>
        <p class="muted">${pins.mine ? "Set. It opens the parent controls as you." : "Not set. Only you can set or change it, from your own login."}</p>${pinForm(true, pins.mine)}
        ${(pins.parents || []).length ? `<p class="muted">Parents with their own PIN: ${esc(namesText(pins.parents))}.</p>` : ""}`
      : `<p>${d.pin_set ? "A parent PIN is set." : "No parent PIN yet."}</p><p class="muted">Only an administrator can set or change PINs.</p>`;
    return `<div class="card"><h2>Parent PIN</h2>
      <p class="muted">On a login that isn't an administrator (the shared screen), <b>Parents</b> asks for a PIN: the family PIN, or a parent's own. It opens the parent controls until <b>Back to Family</b>, or until nobody has tapped for two minutes. After five wrong PINs the pad locks for five minutes and your phones are told. With no PIN set, only an administrator's login opens them.</p>
      ${body}</div>`;
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
    // Dashboards are admins' to change.
    if (!this._data?.is_admin) return;
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
        ${this._picField(m.emoji, "🦖")}
        <label class="field"><span>Color</span><input type="color" name="color" value="${esc(m.color || "#3F51B5")}"></label>
        <label class="field"><span>Allowance (points a week)</span><input type="number" name="allowance" min="0" max="10000" value="${esc(m.allowance || 0)}" style="width:100px"></label>
        ${(this._choices?.tvs || []).length ? `<label class="field"><span>Their chores done unlock</span><span class="inline"><input type="number" name="unlock_minutes" min="0" max="480" value="${esc(m.unlock_minutes || 0)}" style="width:80px" aria-label="Minutes"> min on
          <select name="unlock_tv"><option value="">No TV</option>${this._choices.tvs.map((t) => `<option value="${esc(t.id)}" ${t.id === m.unlock_tv ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select>
          <label class="check"><input type="checkbox" name="unlock_whole_home" ${m.unlock_whole_home ? "checked" : ""}> whole home</label></span>
          <small>Once all of their own chores are done for the day, TV Mgmt gives them this much extra screen time.</small></label>
        <label class="field"><span>Screen-time bank</span><span class="inline"><select name="bank_tv"><option value="">No bank</option>${this._choices.tvs.map((t) => `<option value="${esc(t.id)}" ${t.id === m.bank_tv ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select>
          holds up to <input type="number" name="bank_max" min="15" max="600" value="${esc(m.bank_max || 120)}" style="width:80px" aria-label="Most minutes"> min</span>
          <small>For a TV they use on their own: the minutes it has left at the end of each day are saved, and they can use them another day.</small></label>` : ""}
        <div class="field"><span>Birthday (no year needed)</span><div class="inline">${this._monthDay("birthday", m.birthday, "Birthday")}</div></div>
        <label class="field"><span>Year born (for chores by age)</span><input type="number" name="birth_year" min="1900" max="${new Date().getFullYear()}" value="${esc(m.birth_year ?? "")}" placeholder="Optional" style="width:110px"></label>
        <label class="check" style="align-self:end"><input type="checkbox" name="picture_mode" ${m.picture_mode ? "checked" : ""}> Picture mode <small>(big pictures, tap a chore to hear it)</small></label>
        <label class="field"><span>Home Assistant person</span><select name="person" data-person><option value="">None</option>${people.map((p) => `<option value="${esc(p.entity_id)}" ${p.entity_id === m.person ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
      </div>
      <div class="form-actions"><button class="btn primary" type="submit">Save</button><button class="btn" type="button" data-cancel>Cancel</button></div>
    </form>`;
  }

  // ------------------------------------------------------------------ events

  async _ws(msg) {
    // The parent pass goes with Family's own commands only.
    if (this._pass && msg.type.startsWith(`${DOMAIN}/`)) msg = { ...msg, pass: this._pass };
    return this._hass.callWS(msg);
  }

  // Put the picked emoji or icon into the field the picker was opened from.
  _setPic(value) {
    const t = this._picTarget;
    let field = t?.el;
    if (field && !field.isConnected) field = this.shadowRoot.querySelector(`.pic-field[data-pic-key="${CSS.escape(t.key || "")}"]`);
    this._sheet = null;
    this._picTarget = null;
    this._renderOverlay();
    if (!field) return;
    const input = field.querySelector("input");
    input.value = value;
    field.querySelector(".pic-btn").innerHTML = value ? emo(value) : `<span class="pic-empty">+</span>`;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Show only the icons whose words match the search; a full icon name
  // (mdi:…) can be used even when it isn't in the list.
  _filterPics(query) {
    const q = query.trim().toLowerCase();
    const sheet = this.shadowRoot.querySelector(".pic-sheet");
    if (!sheet) return;
    let shown = 0;
    for (const tile of sheet.querySelectorAll(".pic-grid:not(.emojis) [data-pic-words]")) {
      const hit = !q || q.split(/\s+/).every((w) => tile.dataset.picWords.includes(w) || tile.dataset.picChoose.includes(w));
      tile.hidden = !hit;
      if (hit) shown += 1;
    }
    sheet.querySelector(".pic-grid.emojis").hidden = !!q;
    sheet.querySelector(".pic-emoji-head").hidden = !!q;
    const own = sheet.querySelector(".pic-own");
    const name = q.startsWith("mdi:") ? q : `mdi:${q.replace(/\s+/g, "-")}`;
    const ownOk = q && isIcon(name) && !PICK_ICONS.some(([v]) => v === name);
    own.hidden = !ownOk;
    if (ownOk) {
      const btn = own.querySelector("button");
      btn.dataset.picChoose = name;
      btn.innerHTML = emo(name);
    }
    sheet.querySelector(".pic-none").hidden = shown > 0 || ownOk || !q;
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
    if (ds.photoView) {
      this._sheet = { type: "photo", url: null };
      this._renderOverlay();
      this._ws({ type: `${DOMAIN}/photo`, entry_id: ds.photoView }).then((res) => {
        if (this._sheet?.type !== "photo") return;
        this._sheet.url = res.url || "";
        this._renderOverlay();
      }).catch((err) => this._toast(err?.message || String(err), true));
      return;
    }
    if (ds.how) {
      const chore = this._data.chores.find((c) => c.id === ds.how) || (this._data.all_chores || []).find((c) => c.id === ds.how);
      this._sheet = { type: "how", id: ds.how, name: chore?.name || "", how: chore?.how || "", example: chore?.example ? null : "" };
      this._renderOverlay();
      if (chore?.example) {
        this._ws({ type: `${DOMAIN}/chore/example`, chore_id: ds.how }).then((res) => {
          if (this._sheet?.type !== "how") return;
          this._sheet.example = res.url || "";
          this._renderOverlay();
        }).catch(() => {});
      }
      return;
    }
    if (ds.exampleRemove) {
      this._call({ type: `${DOMAIN}/chore/set_example`, chore_id: ds.exampleRemove, photo: null }, "Photo removed.").then(() => { if (this._edit?.item) this._edit.item.example = false; this._render(); });
      return;
    }
    if (ds.helper && this._sheet?.type === "chore") {
      const list = new Set(this._sheet.helpers || []);
      if (list.has(ds.helper)) list.delete(ds.helper);
      else list.add(ds.helper);
      this._sheet.helpers = [...list];
      this._renderOverlay();
      return;
    }
    if ("meeting" in ds) {
      this._openReport(0, true);
      return;
    }
    if (ds.unpick) {
      this._call({ type: `${DOMAIN}/unpick`, chore_id: ds.unpick }, "Put back in the pool.");
      return;
    }
    if (ds.paidAll) {
      this._call({ type: `${DOMAIN}/paid_all`, member_id: ds.paidAll }, "Marked as paid.");
      return;
    }
    if (ds.pick) {
      const picks = this._data.picks;
      const who = picks?.next;
      if (!who) return;
      this._call({ type: `${DOMAIN}/pick`, member_id: who, chore_id: ds.pick }, `${this._memberById(who)?.name || "They"} picked it.`);
      return;
    }
    if (ds.claim) {
      this._sheet = { type: "claim", id: ds.claim };
      this._renderOverlay();
      return;
    }
    if (ds.claimMember && this._sheet?.type === "claim") {
      const claim = this._sheet.id;
      this._sheet = null;
      this._renderOverlay();
      this._call({ type: `${DOMAIN}/claim`, claim_id: claim, member_id: ds.claimMember }, `Thanks, ${this._memberById(ds.claimMember)?.name || ""}!`);
      return;
    }
    if ("picPick" in ds) {
      const field = el.closest(".pic-field");
      this._picTarget = { el: field, key: field?.dataset.picKey, form: field?.closest("form")?.className || "" };
      this._sheet = { type: "pic" };
      this._renderOverlay();
      this.shadowRoot.querySelector("[data-pic-search]")?.focus();
      return;
    }
    if ("picChoose" in ds && this._sheet?.type === "pic") {
      this._setPic(ds.picChoose);
      return;
    }
    if ("toParents" in ds) {
      this._openParents();
      return;
    }
    if ("toFamily" in ds) {
      this._backToFamily();
      return;
    }
    if (ds.pinKey !== undefined && this._sheet?.type === "pin") {
      const s = this._sheet;
      s.error = "";
      if (ds.pinKey === "del") s.pin = s.pin.slice(0, -1);
      else if (s.pin.length < 8) s.pin += ds.pinKey;
      this._renderOverlay();
      return;
    }
    if ("pinOk" in ds) {
      this._unlock();
      return;
    }
    if ("pinClear" in ds) {
      const own = ds.pinClear === "1";
      this._call({ type: `${DOMAIN}/pin`, pin: null, own }, own ? "Your PIN is removed." : "Family PIN removed.");
      return;
    }
    if (ds.questEdit !== undefined) {
      this._questEdit = ds.questEdit || null;
      this._render();
      return;
    }
    if (ds.petEdit !== undefined) {
      this._petEdit = ds.petEdit || null;
      this._render();
      return;
    }
    if ("statementPrint" in ds) {
      this._printStatement();
      return;
    }
    if ("wake" in ds) {
      this._lastTouch = Date.now();
      this._render();
      return;
    }
    if (ds.freeze) {
      const member = this._memberById(this._member);
      if (member) this._call({ type: `${DOMAIN}/freeze`, member_id: member.id, day: ds.freeze }, "❄️ Streak saved.");
      return;
    }
    if (ds.wish) {
      const member = this._memberById(this._sheet?.member || this._member);
      if (!member) return;
      const on = !(member.wishes || []).includes(ds.wish);
      this._sheet = null;
      this._renderOverlay();
      this._call({ type: `${DOMAIN}/wish`, member_id: member.id, reward_id: ds.wish, on }, on ? "♥ On your wishlist." : "Off your wishlist.");
      return;
    }
    if (ds.quest) {
      if (this._member) this._call({ type: `${DOMAIN}/quest/step`, quest_id: ds.quest, member_id: this._member }, "Step done! 🗺️");
      else {
        this._sheet = { type: "who", what: "quest", id: ds.quest };
        this._renderOverlay();
      }
      return;
    }
    if (ds.pet) {
      if (this._member) this._call({ type: `${DOMAIN}/pet/care`, pet_id: ds.pet, slot: Number(ds.slot), member_id: this._member }, "Thank you! 🐾");
      else {
        this._sheet = { type: "who", what: "pet", id: ds.pet, slot: Number(ds.slot) };
        this._renderOverlay();
      }
      return;
    }
    if (ds.whoDid && this._sheet?.type === "who") {
      const s = this._sheet;
      this._sheet = null;
      this._renderOverlay();
      if (s.what === "trade") this._call({ type: `${DOMAIN}/trade/take`, trade_id: s.id, member_id: ds.whoDid }, "Taken. A parent will say yes or no.");
      else if (s.what === "theme") this._call({ type: `${DOMAIN}/theme/keep`, member_id: ds.whoDid }, "Well done! 🌟");
      else if (s.what === "quest") this._call({ type: `${DOMAIN}/quest/step`, quest_id: s.id, member_id: ds.whoDid }, "Step done! 🗺️");
      else this._call({ type: `${DOMAIN}/pet/care`, pet_id: s.id, slot: s.slot, member_id: ds.whoDid }, "Thank you! 🐾");
      return;
    }
    if (ds.marketTake) {
      if (this._member) this._call({ type: `${DOMAIN}/trade/take`, trade_id: ds.marketTake, member_id: this._member }, "Taken. A parent will say yes or no.");
      else {
        this._sheet = { type: "who", what: "trade", id: ds.marketTake };
        this._renderOverlay();
      }
      return;
    }
    if ("themeKeep" in ds) {
      if (this._member) this._call({ type: `${DOMAIN}/theme/keep`, member_id: this._member }, "Well done! 🌟");
      else {
        this._sheet = { type: "who", what: "theme" };
        this._renderOverlay();
      }
      return;
    }
    if ("questUndo" in ds) {
      this._call({ type: `${DOMAIN}/quest/undo`, quest_id: ds.questUndo }, "Put back.");
      return;
    }
    if (ds.questDelete) {
      this._call({ type: `${DOMAIN}/quest/delete`, quest_id: ds.questDelete }, "Removed.");
      return;
    }
    if (ds.petDelete) {
      this._call({ type: `${DOMAIN}/pet/delete`, pet_id: ds.petDelete }, "Removed.");
      return;
    }
    if ("giveRemove" in ds) {
      this._call({ type: `${DOMAIN}/settings`, give_goal: null }, "Removed.");
      return;
    }
    if ("offer" in ds) {
      this._sheet = { type: "ask", member: this._member, chore: true };
      this._renderOverlay();
      return;
    }
    if (ds.ideaCancel) {
      this._call({ type: `${DOMAIN}/idea/cancel`, idea_id: ds.ideaCancel }, "Taken back.");
      return;
    }
    if (ds.ideaDecide) {
      const yes = ds.yes === "1";
      const box = this.shadowRoot.querySelector(`[data-idea-points="${CSS.escape(ds.ideaDecide)}"]`);
      const msg = { type: `${DOMAIN}/idea/decide`, idea_id: ds.ideaDecide, approved: yes };
      if (yes) {
        if (!box?.value) {
          this._toast("Set how many points it's worth first.", true);
          return;
        }
        msg.points = Number(box.value);
      }
      this._call(msg, yes ? "Added to their chores." : "Told them not this time.");
      return;
    }
    if (ds.mood) {
      const member = this._memberById(this._member);
      if (!member) return;
      const mood = member.mood_today === ds.mood ? null : ds.mood;
      this._call({ type: `${DOMAIN}/mood`, member_id: member.id, mood }, mood ? "Thanks for telling us." : "");
      return;
    }
    if ("give" in ds) {
      this._sheet = { type: "give", member: this._member };
      this._renderOverlay();
      return;
    }
    if (ds.auction) {
      this._sheet = { type: "bid", id: ds.auction, member: this._member };
      this._renderOverlay();
      return;
    }
    if ("homeworkStart" in ds) {
      if (!this._member) {
        this._toast("Open your own page first, then start the timer.", true);
        return;
      }
      (this._focus ||= {})[this._member] = Date.now();
      this._render();
      return;
    }
    if ("homeworkStop" in ds) {
      const member = this._memberById(this._member);
      const start = this._focus?.[this._member];
      if (!member || !start) return;
      delete this._focus[this._member];
      const minutes = Math.round((Date.now() - start) / 60000);
      if (minutes < 1) {
        this._render();
        return;
      }
      this._call({ type: `${DOMAIN}/reading/log`, kind: "homework", member_id: member.id, minutes }, `${minutes} minutes of homework. Nice work, ${member.name}!`);
      return;
    }
    if ("reading" in ds) {
      this._sheet = { type: "reading", member: this._member };
      this._renderOverlay();
      return;
    }
    if ("bank" in ds) {
      this._sheet = { type: "bank", member: this._member };
      this._renderOverlay();
      return;
    }
    if ("gifts" in ds) {
      this._sheet = { type: "gifts", member: this._member };
      this._renderOverlay();
      return;
    }
    if (ds.giftRemove !== undefined && this._sheet?.type === "gifts") {
      const member = this._memberById(this._sheet.member);
      if (member) this._call({ type: `${DOMAIN}/gift_idea`, member_id: member.id, text: ds.giftRemove, add: false }, "").then(() => this._renderOverlay());
      return;
    }
    if ("race" in ds) {
      this._sheet = { type: "race", member: this._member };
      this._renderOverlay();
      return;
    }
    if (ds.raceWho && this._sheet?.type === "race") {
      const member = this._memberById(this._sheet.member);
      this._sheet = null;
      this._renderOverlay();
      this._call({ type: `${DOMAIN}/challenge`, member_id: member?.id, other_id: ds.raceWho }, `Ready, set, go! ${member?.name || ""} vs ${this._memberById(ds.raceWho)?.name || ""}`);
      return;
    }
    if ("ask" in ds) {
      this._sheet = { type: "ask", member: this._member };
      this._renderOverlay();
      return;
    }
    if (ds.requestCancel) {
      this._call({ type: `${DOMAIN}/request/cancel`, request_id: ds.requestCancel }, "Taken back.");
      return;
    }
    if (ds.requestDecide) {
      const yes = ds.yes === "1";
      const box = this.shadowRoot.querySelector(`[data-request-points="${CSS.escape(ds.requestDecide)}"]`);
      const msg = { type: `${DOMAIN}/request/decide`, request_id: ds.requestDecide, approved: yes };
      if (yes) {
        const value = box?.value.trim();
        if (!value) return this._toast("Say how many points it costs.", true);
        msg.points = Math.max(0, Math.round(Number(value) || 0));
      }
      this._call(msg, yes ? "Said yes: it's in their rewards." : "Said no.");
      return;
    }
    if (ds.voteOption !== undefined) {
      const option = Number(ds.voteOption);
      if (this._member) {
        this._call({ type: `${DOMAIN}/vote/cast`, member_id: this._member, option }, "Voted!");
      } else {
        this._sheet = { type: "vote", option };
        this._renderOverlay();
      }
      return;
    }
    if (ds.voteWho && this._sheet?.type === "vote") {
      const option = this._sheet.option;
      this._sheet = null;
      this._call({ type: `${DOMAIN}/vote/cast`, member_id: ds.voteWho, option }, `${this._memberById(ds.voteWho)?.name || "Someone"} voted!`);
      return;
    }
    if ("voteClose" in ds) {
      this._call({ type: `${DOMAIN}/vote/close` }, "Vote closed. The winner is on the meal plan.");
      return;
    }
    if ("voteCancel" in ds) {
      if (!window.confirm("Take the vote down without picking a winner?")) return;
      this._call({ type: `${DOMAIN}/vote/cancel` }, "Vote taken down.");
      return;
    }
    if (ds.countdownDelete) {
      this._call({ type: `${DOMAIN}/countdown/delete`, item_id: ds.countdownDelete }, "Countdown removed.");
      return;
    }
    if ("awayBack" in ds) {
      this._call({ type: `${DOMAIN}/away`, action: "back" }, "Welcome home! Chores are back on from today.");
      return;
    }
    if (ds.awayRemove) {
      this._call({ type: `${DOMAIN}/away`, action: "remove", period_id: ds.awayRemove }, "Trip removed.");
      return;
    }
    if (ds.boostStop) {
      this._call({ type: `${DOMAIN}/boost/stop`, boost_id: ds.boostStop }, "Stopped.");
      return;
    }
    if ("shopping" in ds) {
      this._shopping();
      return;
    }
    if ("reportPrint" in ds) {
      this._printReport();
      return;
    }
    if ("reportShare" in ds) {
      this._shareReport();
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
      // A chore that asks for a photo always opens the sheet, to take it.
      this._sheet = { type: "chore", id: ds.chore, member: who, quick: !!who && !chore?.photo };
      if (who && !chore?.photo) this._confirm();
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
    } else if (ds.tradeOffer) {
      this._sheet = { type: "trade", id: ds.tradeOffer, member: this._member };
      this._renderOverlay();
    } else if (ds.tradeTo !== undefined && this._sheet?.type === "trade") {
      const s = this._sheet;
      this._sheet = null;
      const pay = Math.max(0, Math.round(Number(this.shadowRoot.querySelector("[data-trade-pay]")?.value) || 0));
      const week = !!this.shadowRoot.querySelector("[data-trade-week]")?.checked;
      this._call({ type: `${DOMAIN}/trade/offer`, member_id: s.member, chore_id: s.id, to: ds.tradeTo || null, pay, week }, "Offered. It's still yours until someone takes it and a parent says yes.");
    } else if (ds.tradeTake) {
      this._call({ type: `${DOMAIN}/trade/take`, trade_id: ds.tradeTake, member_id: this._member }, "Taken. A parent will say yes or no.");
    } else if (ds.tradeCancel) {
      this._call({ type: `${DOMAIN}/trade/cancel`, trade_id: ds.tradeCancel }, "Taken back.");
    } else if (ds.tradeDecide) {
      this._call({ type: `${DOMAIN}/trade/decide`, trade_id: ds.tradeDecide, approved: ds.yes === "1" }, ds.yes === "1" ? "Traded for today." : "Trade turned down.");
    } else if ("cashOut" in ds) {
      this._sheet = { type: "cashout", member: this._member, points: "" };
      this._renderOverlay();
    } else if (ds.cashCancel) {
      this._call({ type: `${DOMAIN}/cash_out/cancel`, entry_id: ds.cashCancel }, "Cash out cancelled; the points are back.");
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
    } else if (ds.goalRemove) {
      this._call({ type: `${DOMAIN}/family_goal/delete`, item_id: ds.goalRemove }, "Goal removed.");
    } else if (ds.goalEdit !== undefined) {
      this._goalEdit = ds.goalEdit || null;
      this._render();
    } else if ("themeRemove" in ds) {
      this._call({ type: `${DOMAIN}/settings`, theme_week: null }, "Theme week removed.");
    } else if ("payoutsLoad" in ds) {
      this._ws({ type: `${DOMAIN}/payouts` }).then((res) => {
        this._payouts = res.months;
        this._render();
      }).catch((err) => this._toast(err?.message || String(err), true));
    } else if ("payoutsCsv" in ds) {
      this._payoutsCsv();
    } else if (ds.photosMonth !== undefined) {
      this._openPhotos(Number(ds.photosMonth) || 0);
    } else if ("photosPrint" in ds) {
      this._printPhotos();
    } else if (ds.auctionClose) {
      this._call({ type: `${DOMAIN}/auction/close`, auction_id: ds.auctionClose }, "Auction closed.");
    } else if (ds.auctionCancel) {
      this._call({ type: `${DOMAIN}/auction/cancel`, auction_id: ds.auctionCancel }, "Auction cancelled.");
    } else if (ds.giftShare) {
      this._shareGifts(ds.giftShare);
    } else if (ds.quick !== undefined && ds.memberId) {
      const button = (this._data.settings?.quick_points || [])[Number(ds.quick)];
      const m = this._memberById(ds.memberId);
      if (!button || !m || this._busy) return;
      const sign = button.points > 0 ? "+" : "−";
      this._call({ type: `${DOMAIN}/adjust`, member_id: m.id, points: button.points, reason: `${emoText(button.emoji) ? `${button.emoji} ` : ""}${button.label}` }, `${m.name}: ${sign}${pts(Math.abs(button.points))} for ${button.label}`);
    } else if (ds.new) {
      this._edit = { collection: ds.new, item: null };
      this._rewardKind = null;
      this._render();
    } else if (ds.holdOpen) {
      this._holdFor = ds.holdOpen;
      this._holdChoice = "1";
      this._render();
    } else if ("holdCancel" in ds) {
      this._holdFor = null;
      this._render();
    } else if (ds.holdLift) {
      this._call({ type: `${DOMAIN}/hold`, member_id: ds.holdLift, lift: true }, "Hold lifted.");
    } else if (ds.edit) {
      const list = ds.edit === "chores" ? this._data.all_chores : ds.edit === "routines" ? this._data.all_routines : this._data[ds.edit];
      this._edit = { collection: ds.edit, item: list.find((x) => x.id === ds.id) };
      this._rewardKind = null;
      this._render();
      this.shadowRoot.querySelector(".edit-row")?.previousElementSibling?.scrollIntoView?.({ block: "start", behavior: "smooth" });
    } else if ("cancel" in ds) {
      this._edit = null;
      this._render();
    } else if (ds.delete) {
      const what = { controls: "this from the Family dashboard", chores: "this chore", rewards: "this reward", members: "this family member and their points", todo_lists: "this to-do list from Family (the list itself stays)" }[ds.delete];
      if (!window.confirm(`Remove ${what}?`)) return;
      this._call({ type: `${DOMAIN}/delete`, collection: ds.delete, item_id: ds.id }, "Removed.").then((ok) => {
        if (ok && ds.delete === "members") this._followMembers();
      });
    } else if (ds.didnt) {
      const entry = [...(this._data.to_check || []), ...this._historyAll()].find((e) => e.id === ds.didnt);
      const box = this.shadowRoot.querySelector(`[data-penalty-for="${CSS.escape(ds.didnt)}"]`);
      this._sheet = { type: "didnt", id: ds.didnt, title: entry?.title || "", member: entry?.member, penalty: box && box.value.trim() !== "" ? Math.max(0, Math.round(Number(box.value) || 0)) : null, reason: "" };
      this._renderOverlay();
    } else if (ds.reason !== undefined && (this._sheet?.type === "didnt" || this._sheet?.type === "didnt_all")) {
      const input = this.shadowRoot.querySelector("[data-didnt-form] [name=reason], [data-didnt-all-form] [name=reason]");
      if (input) input.value = ds.reason;
    } else if (ds.reviewAll !== undefined) {
      const ids = (this._data.to_check || []).map((e) => e.id);
      if (!ids.length || this._busy) return;
      if (ds.reviewAll === "1") {
        this._call({ type: `${DOMAIN}/review_all`, entry_ids: ids, approved: true }, `${ids.length} chores checked.`);
      } else {
        this._sheet = { type: "didnt_all", ids, penalties: this._penaltyBoxes(ids) };
        this._renderOverlay();
      }
    } else if (ds.historyMore !== undefined) {
      this._historyMoreLoad();
    } else if (ds.historyCsv !== undefined) {
      this._historyCsv();
    } else if (ds.say !== undefined) {
      if (!say(ds.say)) this._toast("This screen can't read out loud.", true);
    } else if (ds.timer) {
      this._startTimer(ds.timer);
    } else if (ds.timerStop) {
      delete (this._timers || {})[ds.timerStop];
      this._render();
    } else if (ds.link) {
      const link = (this._data.links || []).find((l) => l.id === ds.link);
      if (link) {
        this._sheet = { type: "link", id: link.id };
        this._renderOverlay();
      }
    } else if (ds.linkAdd !== undefined) {
      const rows = this.shadowRoot.querySelector("[data-link-rows]");
      if (rows) rows.insertAdjacentHTML("beforeend", this._linkRow({}));
    } else if (ds.linkRemove !== undefined) {
      ev.target.closest("[data-link-row]")?.remove();
    } else if (ds.story) {
      this._openStory(ds.story);
    } else if (ds.highFive) {
      this._sheet = { type: "high5", from: ds.highFive, emoji: "🙌" };
      this._renderOverlay();
    } else if (ds.fiveEmoji && this._sheet?.type === "high5") {
      this._sheet.emoji = ds.fiveEmoji;
      this._renderOverlay();
    } else if (ds.fiveTo && this._sheet?.type === "high5") {
      this._sendHighFive(this._sheet.from, ds.fiveTo, this._sheet.emoji);
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
    if (ev.target.dataset.goalWho !== undefined) {
      const people = ev.target.closest("form")?.querySelector(".goal-people");
      if (people) people.hidden = ev.target.value !== "some";
      return;
    }
    if (ev.target.dataset.exampleInput !== undefined) {
      const file = ev.target.files?.[0];
      const choreId = ev.target.dataset.exampleInput;
      if (file) {
        shrinkPhoto(file)
          .then((url) => this._call({ type: `${DOMAIN}/chore/set_example`, chore_id: choreId, photo: url }, "Photo saved."))
          .then(() => { if (this._edit?.item) this._edit.item.example = true; this._render(); })
          .catch(() => this._toast("That photo couldn't be read. Try again.", true));
      }
      return;
    }
    if (ev.target.dataset.photoInput !== undefined) {
      const file = ev.target.files?.[0];
      if (file && this._sheet) {
        shrinkPhoto(file).then((url) => {
          if (!this._sheet) return;
          this._sheet.photo = url;
          this._renderOverlay();
        }).catch(() => this._toast("That photo couldn't be read. Try again.", true));
      }
      return;
    }
    if (ev.target.dataset.holdChoice !== undefined) {
      const form = ev.target.closest("form");
      const reason = form?.querySelector('[name="reason"]')?.value || "";
      this._holdChoice = ev.target.value;
      this._render();
      const again = this.shadowRoot.querySelector('[data-hold-form] [name="reason"]');
      if (again) again.value = reason;
      return;
    }
    if (ev.target.dataset.historyKind !== undefined) {
      this._historyFilter = { ...(this._historyFilter || { text: "", member: "" }), kind: ev.target.value };
      this._refreshHistoryList();
      return;
    }
    if (ev.target.dataset.historyMember !== undefined) {
      this._historyFilter = { ...(this._historyFilter || { text: "" }), member: ev.target.value };
      const list = this.shadowRoot.querySelector("[data-history-list]");
      if (list) list.innerHTML = this._historyList();
      return;
    }
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
    if (ev.target?.dataset?.speakerFind !== undefined) {
      const q = ev.target.value.trim().toLowerCase();
      for (const label of ev.target.closest("details").querySelectorAll("[data-speaker-name]")) label.hidden = !!q && !label.dataset.speakerName.includes(q);
      return;
    }
    if (ev.target?.dataset?.picSearch !== undefined) {
      this._filterPics(ev.target.value);
      return;
    }
    if (ev.target?.dataset?.cashoutPoints !== undefined && this._sheet?.type === "cashout") {
      this._sheet.points = ev.target.value;
      const preview = this.shadowRoot.querySelector(".cash-preview");
      const n = Number(ev.target.value) || 0;
      if (preview) preview.textContent = n > 0 ? `= ${money(n, this._data.money)}` : "";
      return;
    }
    if (ev.target.dataset.historyText !== undefined) {
      this._historyFilter = { ...(this._historyFilter || { member: "" }), text: ev.target.value };
      const list = this.shadowRoot.querySelector("[data-history-list]");
      if (list) list.innerHTML = this._historyList();
      return;
    }
    if (ev.target.dataset.filter === undefined) return;
    // Narrow the entity list as a parent types, keeping what's picked.
    const select = ev.target.closest("form").querySelector('select[name="entity_id"]');
    select.innerHTML = this._entityOptions(ev.target.value, select.value);
  }

  _formValues(form) {
    const data = new FormData(form);
    const out = {};
    for (const [key, value] of data.entries()) {
      if (key === "members" || key === "days" || key === "notify_targets" || key === "remind_speakers" || key === "chores") (out[key] ||= []).push(value);
      else out[key] = value;
    }
    return out;
  }

  async _onSubmit(ev) {
    ev.preventDefault();
    const form = ev.target;
    if (form.matches("[data-cashout-form]")) {
      const s = this._sheet;
      const member = this._memberById(s?.member);
      const points = Number(form.querySelector("[name=points]").value);
      if (!member || this._busy) return;
      this._busy = true;
      try {
        const res = await this._ws({ type: `${DOMAIN}/cash_out`, member_id: member.id, points });
        this._sheet = null;
        this._toast(`${res.entry.title} asked for, ${member.name}. A parent will pay it out.`);
        this._badgeToast(member, res.badges);
        await this._load();
      } catch (err) {
        this._toast(err?.message || String(err), true);
      } finally {
        this._busy = false;
        this._renderOverlay();
      }
      return;
    }
    if (form.matches("[data-pin-form]")) {
      const pin = form.querySelector("[name=pin]").value.trim();
      const own = form.dataset.own === "1";
      await this._call({ type: `${DOMAIN}/pin`, pin, own }, own ? "Your PIN is saved." : "Family PIN saved.");
      return;
    }
    if (form.dataset.penaltySetting !== undefined) {
      const value = Math.max(0, Math.round(Number(this._formValues(form).penalty) || 0));
      return this._call({ type: `${DOMAIN}/settings`, penalty: value }, "Saved.");
    }
    if (form.dataset.phones !== undefined) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/settings`, notify_targets: v.notify_targets || [], notify_done: !!v.notify_done, notify_rewards: !!v.notify_rewards, weekly_summary: !!v.weekly_summary, live_activity: !!v.live_activity, live_per_child: !!v.live_per_child, live_from: v.live_from || null }, "Saved.");
    }
    if (form.dataset.goalForm !== undefined) {
      const v = this._formValues(form);
      const ok = await this._call({ type: `${DOMAIN}/family_goal/save`, item_id: v.id || null, name: v.name, emoji: v.emoji || null, target: Math.round(Number(v.target) || 0), restart: !!v.restart, kids: v.who === "kids", members: v.who === "some" ? v.members || [] : null }, "Saved.");
      if (ok) {
        this._goalEdit = null;
        this._render();
      }
      return;
    }
    if (form.dataset.auctionForm !== undefined) {
      const v = this._formValues(form);
      const members = this._rewardMembers(v);
      return this._call({ type: `${DOMAIN}/auction/start`, name: v.name, emoji: v.emoji || null, points: Math.round(Number(v.points) || 0), minutes: Math.round(Number(v.minutes) || 0), members }, "Auction started.");
    }
    if (form.matches("[data-bid-form]")) {
      const v = this._formValues(form);
      const s = this._sheet;
      const member = this._memberById(v.member_id || s?.member);
      if (!member || this._busy) return;
      this._sheet = null;
      this._renderOverlay();
      return this._call({ type: `${DOMAIN}/auction/bid`, auction_id: s.id, member_id: member.id, points: Math.round(Number(v.points) || 0) }, `Bid in, ${member.name}!`);
    }
    if (form.matches("[data-reading-form]")) {
      const v = this._formValues(form);
      const member = this._memberById(v.member_id || this._sheet?.member);
      if (!member || this._busy) return;
      this._sheet = null;
      this._renderOverlay();
      return this._call({ type: `${DOMAIN}/reading/log`, member_id: member.id, minutes: Math.round(Number(v.minutes) || 0), book: v.book || null }, `Nice reading, ${member.name}! 📚`);
    }
    if (form.matches("[data-gift-form]")) {
      const v = this._formValues(form);
      const member = this._memberById(this._sheet?.member);
      if (!member || this._busy || !String(v.text || "").trim()) return;
      await this._call({ type: `${DOMAIN}/gift_idea`, member_id: member.id, text: v.text, add: true }, "Added.");
      this._renderOverlay();
      return;
    }
    if (form.matches("[data-bank-form]")) {
      const v = this._formValues(form);
      const member = this._memberById(this._sheet?.member);
      if (!member || this._busy) return;
      this._sheet = null;
      this._renderOverlay();
      const minutes = Math.round(Number(v.minutes) || 0);
      return this._call({ type: `${DOMAIN}/bank/spend`, member_id: member.id, minutes }, `${minutes} more minutes of TV today, ${member.name}.`);
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
          members: li.querySelector("[data-eligible]") ? this._rewardMembers({ members: [...li.querySelectorAll('input[name="members"]:checked')].map((el) => el.value) }) : null,
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
      return this._call({ type: `${DOMAIN}/meals`, date: form.dataset.meals, breakfast: v.breakfast || "", lunch: v.lunch || "", dinner: v.dinner || "", ingredients: v.ingredients || "" }, "Meals saved.");
    }
    if (form.matches("[data-pic-form]")) {
      const v = form.querySelector("[name=pic]").value.trim();
      if (v) this._setPic(v);
      return;
    }
    if (form.matches("[data-didnt-all-form]")) {
      const s = this._sheet;
      if (!s || this._busy) return;
      const reason = form.querySelector("[name=reason]")?.value.trim() || null;
      const msg = { type: `${DOMAIN}/review_all`, entry_ids: s.ids, approved: false, reason };
      if (Object.keys(s.penalties).length) msg.penalties = s.penalties;
      this._sheet = null;
      this._renderOverlay();
      return this._call(msg, "Points taken back.");
    }
    if (form.matches("[data-didnt-form]")) {
      const s = this._sheet;
      if (!s || this._busy) return;
      const reason = form.querySelector("[name=reason]")?.value.trim() || null;
      const msg = { type: `${DOMAIN}/review`, entry_id: s.id, approved: false, reason };
      if (s.penalty != null) msg.penalty = s.penalty;
      this._sheet = null;
      this._renderOverlay();
      return this._call(msg, "Points taken back.");
    }
    if (form.matches("[data-links-form]")) {
      const links = [...form.querySelectorAll("[data-link-row]")].map((row) => ({
        id: row.dataset.linkRow || null,
        name: row.querySelector("[name=name]").value,
        emoji: row.querySelector("[name=emoji]").value,
        url: row.querySelector("[name=url]").value,
        member: row.querySelector("[name=member]").value || null,
        mobile: row.querySelector("[name=mobile]").checked,
      })).filter((l) => l.name.trim() || l.url.trim());
      return this._call({ type: `${DOMAIN}/settings`, links }, "Links saved.");
    }
    if (form.matches("[data-weather-form]")) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/settings`, weather_entity: v.weather_entity || null }, "Saved.");
    }
    if (form.matches("[data-give-form]")) {
      const v = this._formValues(form);
      const member = this._memberById(this._sheet?.member);
      if (!member || this._busy) return;
      this._sheet = null;
      this._renderOverlay();
      return this._call({ type: `${DOMAIN}/give`, member_id: member.id, points: Math.round(Number(v.points) || 0) }, `Thank you, ${member.name}! 💝`);
    }
    if (form.matches("[data-ask-form]")) {
      const v = this._formValues(form);
      const member = this._memberById(this._sheet?.member);
      if (!member || this._busy || !String(v.name || "").trim()) return;
      this._busy = true;
      try {
        const chore = !!this._sheet?.chore;
        await this._ws({ type: `${DOMAIN}/${chore ? "idea" : "request"}/add`, member_id: member.id, name: v.name, emoji: v.emoji || null, points: v.points === "" ? null : Number(v.points) });
        this._sheet = null;
        this._toast(chore ? `Offered! A parent will say yes or no, ${member.name}.` : `Asked! A parent will say yes or no, ${member.name}.`);
        await this._load();
      } catch (err) {
        this._toast(err?.message || String(err), true);
      } finally {
        this._busy = false;
        this._renderOverlay();
      }
      return;
    }
    if (form.dataset.voteForm !== undefined) {
      const v = this._formValues(form);
      const options = String(v.options || "").split("\n").map((x) => x.trim()).filter(Boolean);
      return this._call({ type: `${DOMAIN}/vote/start`, options, date: v.date || null, closes: v.closes || null }, "Vote started. It's on the Family dashboard.");
    }
    if (form.dataset.countdownForm !== undefined) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/countdown/save`, name: v.name, emoji: v.emoji || null, date: v.date, member: v.member || null }, "Countdown added.");
    }
    if (form.dataset.awayForm !== undefined) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/away`, action: "add", from: v.from || null, until: v.until || null }, v.from && v.from > localDayIso(0) ? "Trip planned." : "Away: chores are off.");
    }
    if (form.dataset.boostForm !== undefined) {
      const v = this._formValues(form);
      if (!v.until) return this._toast("Pick when it ends.", true);
      return this._call({ type: `${DOMAIN}/boost/start`, label: v.label || null, factor: Number(v.factor || 2), until: v.until, chores: v.chores?.length ? v.chores : null }, "Double points on!");
    }
    if (form.dataset.calendarAdd !== undefined) {
      const v = this._formValues(form);
      const msg = { type: `${DOMAIN}/calendar/add`, entity_id: v.entity_id, title: v.title, date: v.date };
      if (v.start) Object.assign(msg, { start: v.start, end: v.end || null });
      else if (v.end_date) msg.end_date = v.end_date;
      const ok = await this._call(msg, "Added to the calendar.");
      if (ok) form.reset();
      return;
    }
    if (form.dataset.pickForm !== undefined) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/settings`, pick_points: Math.max(0, Math.round(Number(v.pick_points) || 0)) }, "Saved.");
    }
    if (form.dataset.giveGoalForm !== undefined) {
      const v = this._formValues(form);
      if (!String(v.name || "").trim()) {
        this._toast("Say what the family gives for.", true);
        return;
      }
      return this._call({ type: `${DOMAIN}/settings`, give_goal: { name: v.name, emoji: v.emoji || null, target: Math.max(1, Math.round(Number(v.target) || 0)) }, restart_give: !!v.restart, give_percent: Math.max(0, Math.min(50, Math.round(Number(v.give_percent) || 0))) }, "Saved.");
    }
    if (form.dataset.gradeForm !== undefined) {
      const v = this._formValues(form);
      return this._call({ type: `${DOMAIN}/grade/add`, member_id: v.member_id, subject: v.subject || null, grade: v.grade }, "Points given. 🎓");
    }
    if (form.dataset.themeForm !== undefined) {
      const v = this._formValues(form);
      if (!v.name || !v.from || !v.until) return this._toast("Give the theme and its first and last day.", true);
      return this._call({ type: `${DOMAIN}/settings`, theme_week: { name: v.name, emoji: v.emoji || null, points: Math.max(0, Math.round(Number(v.points) || 0)), from: v.from, until: v.until } }, "Theme week saved.");
    }
    if (form.dataset.extrasForm !== undefined) {
      const v = this._formValues(form);
      const number = (x) => Math.max(0, Math.round(Number(x) || 0));
      const percent = (x) => Math.min(100, number(x));
      return this._call({
        type: `${DOMAIN}/settings`,
        reading: { block_minutes: Math.min(240, number(v.reading_block)), points: number(v.reading_points), max_minutes: Math.min(600, number(v.reading_max)) },
        allowance_rule: { enabled: !!v.rule_enabled, boost_at: percent(v.boost_at), boost: percent(v.boost), cut_below: Math.min(percent(v.cut_below), percent(v.boost_at)), cut: percent(v.cut) },
        beat_clock_points: number(v.beat_clock_points),
        homework: { block_minutes: Math.min(240, number(v.homework_block)), points: number(v.homework_points), max_minutes: Math.min(600, number(v.homework_max)) },
        age_points: number(v.age_percent) ? { percent: Math.min(50, number(v.age_percent)), from_age: Math.min(18, number(v.age_from)) } : null,
        reward_list: v.reward_list || null,
        helper_bonus: number(v.helper_bonus),
        grade_points: Object.fromEntries(String(v.grades || "").split(",").map((x) => x.split("=").map((y) => y.trim())).filter(([g, p]) => g && p !== undefined && p !== "").map(([g, p]) => [g, Math.max(0, Math.round(Number(p) || 0))])),
      }, "Saved.");
    }
    if (form.dataset.funForm !== undefined) {
      const v = this._formValues(form);
      const number = (x) => Math.max(0, Math.round(Number(x) || 0));
      return this._call({ type: `${DOMAIN}/settings`, bingo_line: number(v.bingo_line), bingo_full: number(v.bingo_full), challenge_points: number(v.challenge_points), mood_check: !!v.mood_check, freeze_cost: number(v.freeze_cost), quiet_from: v.quiet_from && v.quiet_until ? v.quiet_from : null, quiet_until: v.quiet_from && v.quiet_until ? v.quiet_until : null }, "Saved.");
    }
    if (form.dataset.statementForm !== undefined) {
      const v = this._formValues(form);
      this._sheet = { type: "statement", statement: null };
      this._renderOverlay();
      try {
        const result = await this._ws({ type: `${DOMAIN}/statement`, member_id: v.member_id, months_ago: Number(v.months_ago) || 0 });
        this._sheet = { type: "statement", statement: result.statement };
      } catch (err) {
        this._sheet = null;
        this._toast(err?.message || String(err), true);
      }
      this._renderOverlay();
      return;
    }
    if (form.dataset.questForm !== undefined) {
      const v = this._formValues(form);
      const steps = String(v.steps || "").split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
        const m = line.match(/^(.*?)\s*\[(\d+)\]\s*$/);
        return m ? { name: m[1], points: Number(m[2]) } : { name: line, points: 0 };
      });
      const members = this._rewardMembers(v);
      this._questEdit = null;
      return this._call({ type: `${DOMAIN}/quest/save`, quest: { id: v.id || null, name: v.name, emoji: v.emoji || null, steps, members } }, "Saved.");
    }
    if (form.dataset.petForm !== undefined) {
      const v = this._formValues(form);
      this._petEdit = null;
      return this._call({ type: `${DOMAIN}/pet/save`, pet: { id: v.id || null, name: v.name, emoji: v.emoji || null, task: v.task, times: String(v.times || "").split(",").map((t) => t.trim()).filter(Boolean), points: Math.max(0, Math.round(Number(v.points) || 0)) } }, "Saved.");
    }
    if (form.dataset.leaveForm !== undefined) {
      const v = this._formValues(form);
      const times = Object.fromEntries(WEEKDAY_NAMES.map((_n, i) => [String(i), v[`day${i}`] || null]).filter(([, t]) => t));
      return this._call({ type: `${DOMAIN}/settings`, leave_times: times, leave_warn: Math.max(1, Math.min(120, Math.round(Number(v.leave_warn) || 30))) }, "Saved.");
    }
    if (form.dataset.savingForm !== undefined) {
      const v = this._formValues(form);
      const number = (x) => Math.max(0, Math.round(Number(x) || 0));
      return this._call({ type: `${DOMAIN}/settings`, saving_percent: number(v.saving_percent), saving_max: number(v.saving_max), birthday_points: number(v.birthday_points), goal_match: Math.min(100, number(v.goal_match)) }, "Saved.");
    }
    if (form.dataset.reportForm !== undefined) {
      const v = this._formValues(form);
      this._openReport(Number(v.weeks_ago || 0));
      return;
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
    if (form.dataset.holdForm) {
      const v = this._formValues(form);
      const msg = { type: `${DOMAIN}/hold`, member_id: form.dataset.holdForm, reason: v.reason || null };
      if (v.for === "until") {
        if (!v.until) return this._toast("Pick the last day of the hold.", true);
        msg.until = v.until;
      } else msg.days = Number(v.for);
      this._holdFor = null;
      return this._call(msg, "Rewards on hold.");
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
      item = { min_age: v.min_age === "" || v.min_age == null ? null : Number(v.min_age), max_age: v.max_age === "" || v.max_age == null ? null : Number(v.max_age), timer_minutes: Math.max(0, Math.round(Number(v.timer_minutes) || 0)), timer_bonus: Math.max(0, Math.round(Number(v.timer_bonus) || 0)), remind_time: v.remind_time || null, remind_speakers: v.remind_speakers || [], name: v.name, emoji: v.emoji, points: Number(v.points || 0), penalty: v.penalty === "" ? null : Number(v.penalty), repeat: v.repeat, repeat_days: Number(v.repeat_days || 1), todo_list: v.todo_list || null, due_only: !!v.due_only && !!v.todo_list, photo: v.photo || "", how: v.how || "", streak_days: Math.max(0, Math.round(Number(v.streak_days) || 0)), streak_bonus: Math.max(0, Math.round(Number(v.streak_bonus) || 0)), pool: !!v.pool, team: v.grab === "team", difficulty: v.difficulty || "", done_when: v.done_entity ? { entity_id: v.done_entity.trim(), state: (v.done_state || "").trim() } : null, only_when: v.only_entity ? { entity_id: v.only_entity.trim(), states: String(v.only_states || "").split(",").map((x) => x.trim()).filter(Boolean) } : null, on_done: v.on_done || null, members: v.members || [], grab: v.grab === "1", enabled: !!v.enabled, days: (v.days || []).map(Number), from_time: v.from_time || null, until_time: v.until_time || null, turns: !!v.turns, turn_every: v.turn_every || "time", turn_first: v.turn_first || null, from_date: v.from_month && v.from_day ? `${v.from_month}-${v.from_day}` : null, until_date: v.until_month && v.until_day ? `${v.until_month}-${v.until_day}` : null };
    } else if (collection === "routines") {
      item = { name: v.name, emoji: v.emoji, points: Number(v.points || 0), members: v.members || [], steps: (v.steps || "").split("\n").map((x) => x.trim()).filter(Boolean), days: (v.days || []).map(Number), from_time: v.from_time || null, until_time: v.until_time || null, enabled: !!v.enabled, beat_clock: !!v.beat_clock };
    } else if (collection === "rewards") {
      // All ticked: anyone, including people added later. A shorter list:
      // only those people. Nobody ticked: the reward is unavailable.
      item = { name: v.name, emoji: v.emoji, points: Number(v.points || 0), kind: v.kind, limit: v.limit || null, shop_days: (v.shop_days || []).map(Number), tv: v.tv, speaker: v.speaker, minutes: Number(v.minutes || 0), whole_home: !!v.whole_home, members: this._rewardMembers(v) };
    } else if (collection === "controls") {
      item = { entity_id: v.entity_id, name: v.name, emoji: v.emoji, members: v.members || [], confirm: !!v.confirm };
    } else if (collection === "members") {
      item = { bank_tv: v.bank_tv || null, bank_max: Math.max(15, Math.min(600, Math.round(Number(v.bank_max) || 120))), unlock_tv: v.unlock_tv || null, unlock_minutes: Math.max(0, Math.round(Number(v.unlock_minutes) || 0)), unlock_whole_home: !!v.unlock_whole_home, name: v.name, emoji: v.emoji, color: v.color, person: v.person || null, allowance: Math.max(0, Math.round(Number(v.allowance) || 0)), birthday: v.birthday_month && v.birthday_day ? `${v.birthday_month}-${v.birthday_day}` : null, birth_year: v.birth_year ? Number(v.birth_year) : null, picture_mode: !!v.picture_mode };
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
        const timer = this._timers?.[s.id];
        const res = await this._ws({ type: `${DOMAIN}/complete`, member_id: s.member, chore_id: s.id, timer_started: timer ? new Date(timer.start).toISOString() : null, ...(s.photo ? { photo: s.photo } : {}), ...((s.helpers || []).length ? { helpers: s.helpers } : {}) });
        if (timer) delete this._timers[s.id];
        const bonus = (res.entry?.bonuses || []).map((b) => (b.points ? ` ${b.title} +${pts(b.points)}` : ` ${b.title}`)).join("");
        const waiting = res.entry?.team_waiting || [];
        this._toast(waiting.length
          ? `Great job, ${member.name}! Your ${pts(chore?.points ?? 0)} count once ${namesText(waiting)} ${waiting.length === 1 ? "has" : "have"} done it too.`
          : `Great job, ${member.name}! +${pts(chore?.points ?? 0)}.${bonus} (${res.points} now)`, false, res.entry?.id);
        if ((res.entry?.bonuses || []).some((b) => b.bonus === "all_done")) this._celebrate(member);
        this._badgeToast(member, res.badges);
      } else {
        const reward = this._data.rewards.find((r) => r.id === s.id);
        const res = await this._ws({ type: `${DOMAIN}/redeem`, member_id: s.member, reward_id: s.id });
        this._toast(`Enjoy ${reward?.name || "it"}, ${member.name}! ${pts(res.points)} left`, false, res.entry?.id);
        this._badgeToast(member, res.badges);
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

  // `member`: a family member's id, to show only their page. `wall`: the
  // big wall view, for a TV or a tablet on the wall.
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
