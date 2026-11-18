// The Family card's loader (family-card.js, 2.16.0): on every dashboard page,
// it defines `family-card` straight away and imports the big Family script
// only when a card is shown, once for every card on the page.
// Run with: node --test tests/*.mjs
import { test } from "node:test";
import assert from "node:assert/strict";

const defined = new Map();
const waiting = new Map();

class FakeElement {
  constructor() {
    this.style = {};
    this.children = [];
    this.textContent = "";
    this.isConnected = false;
  }

  replaceChildren(...children) {
    this.children = children;
  }
}

globalThis.HTMLElement = FakeElement;
globalThis.window = globalThis;
globalThis.customElements = {
  define(name, cls) {
    defined.set(name, cls);
    for (const resolve of waiting.get(name) || []) resolve(cls);
  },
  get(name) {
    return defined.get(name);
  },
  whenDefined(name) {
    if (defined.has(name)) return Promise.resolve(defined.get(name));
    return new Promise((resolve) => waiting.set(name, [...(waiting.get(name) || []), resolve]));
  },
};
globalThis.document = {
  createElement(name) {
    const cls = defined.get(name);
    if (!cls) throw new Error(`${name} isn't defined`);
    return new cls();
  },
};

// What family-panel.js defines: the real card.
class FakeView extends FakeElement {
  setConfig(config) {
    this.config = config;
  }

  set hass(hass) {
    this.gotHass = hass;
  }
}

const loader = await import("../custom_components/family/frontend/family-card.js?v=2.16.0");
const imported = [];
// The page's one import, made by the first card; here a fake panel script.
const first = loader.loadPanel(async (url) => {
  imported.push(url);
  customElements.define("family-card-view", FakeView);
});

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test("the card is known at once, without the Family script", () => {
  assert.ok(defined.has("family-card"));
  assert.ok(window.customCards.some((c) => c.type === "family-card"));
  const Card = defined.get("family-card");
  assert.deepEqual(Card.getStubConfig(), {});
  assert.equal(new Card().getCardSize(), 12);
  assert.deepEqual(new Card().getGridOptions(), { columns: "full", min_rows: 6 });
});

test("the Family script is imported once, with the same version", async () => {
  await first;
  assert.equal(imported.length, 1);
  const url = new URL(imported[0]);
  assert.ok(url.pathname.endsWith("/custom_components/family/frontend/family-panel.js"));
  assert.equal(url.search, "?v=2.16.0");
});

test("a shown card makes the real card with its config and hass", async () => {
  const Card = defined.get("family-card");
  const card = new Card();
  card.setConfig({ member: "alex" });
  card.hass = { user: "one" };
  card.isConnected = true;
  card.connectedCallback();
  await settle();
  assert.equal(card.style.display, "block");
  const [inner] = card.children;
  assert.ok(inner instanceof FakeView);
  assert.deepEqual(inner.config, { member: "alex" });
  assert.deepEqual(inner.gotHass, { user: "one" });
  // Later updates go straight to the real card.
  card.hass = { user: "two" };
  card.setConfig({ wall: true });
  assert.deepEqual(inner.gotHass, { user: "two" });
  assert.deepEqual(inner.config, { wall: true });
  // A second card on the page doesn't import it again.
  const other = new Card();
  other.setConfig({});
  other.isConnected = true;
  other.connectedCallback();
  await settle();
  assert.ok(other.children[0] instanceof FakeView);
  assert.equal(imported.length, 1);
});

test("a script that can't load says so, and tries again when shown again", async () => {
  // Another copy of the loader (another version), whose import fails once.
  defined.delete("family-card");
  const again = await import("../custom_components/family/frontend/family-card.js?v=fail");
  const Card = defined.get("family-card");
  let tries = 0;
  const failing = again.loadPanel(async () => {
    tries += 1;
    throw new Error("offline");
  });
  await assert.rejects(failing);
  const card = new Card();
  card.setConfig({});
  card.isConnected = true;
  // The rejected import was forgotten, so this card's own load imports
  // the (real, here: unreachable) script; make that fail too.
  again.loadPanel(async () => {
    tries += 1;
    throw new Error("still offline");
  });
  card.connectedCallback();
  await settle();
  await settle();
  assert.match(card.textContent, /couldn't load/);
  const before = tries;
  card.hass = { user: "one" }; // not on every hass update
  await settle();
  assert.equal(tries, before);
  // Shown again: one more try, which works this time.
  again.loadPanel(async () => {
    tries += 1;
    customElements.define("family-card-view", FakeView);
  });
  card.connectedCallback();
  await settle();
  await settle();
  assert.ok(card.children[0] instanceof FakeView);
});
