/*
 * The Family card's loader (2.16.0), loaded on every dashboard page with
 * frontend.add_extra_js_url.
 *
 * The Family dashboard script (family-panel.js) is big. Before 2.16.0 it was
 * what every page loaded, for every login, just so the `family-card` card was
 * known. Now only this small file is: it defines `family-card` (so a
 * dashboard and the card picker know it at once) and imports family-panel.js
 * the first time a card is shown, then puts the real card,
 * `family-card-view`, inside itself and hands it the card's config and
 * `hass`. Opening the Family sidebar page loads the same script, so it's
 * fetched once either way.
 *
 * The version in this script's own URL (`?v=`) is passed on to the panel
 * script's URL, so both are fetched again after an update and can be kept by
 * the browser in between.
 */

const VIEW = "family-card-view";

// family-panel.js next to this file, with this file's `?v=` version.
function panelUrl() {
  const own = new URL(import.meta.url);
  const url = new URL("./family-panel.js", own);
  url.search = own.search;
  return url.href;
}

// One import for every card on the page (and none if no card is shown).
let loading = null;
export function loadPanel(importer = (url) => import(url)) {
  if (!loading) {
    loading = importer(panelUrl()).catch((err) => {
      loading = null; // a later card (or a reload of this one) tries again
      throw err;
    });
  }
  return loading;
}

class FamilyCardLoader extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._inner = null;
    this._pending = null;
    // The script couldn't be loaded: don't try again on every `hass` update,
    // only when the card is shown again (connected).
    this._failed = false;
  }

  // `member` (one family member's page), `wall` (the wall view), `phone`:
  // see the README. Kept here and handed to the real card when it's made.
  setConfig(config) {
    this._config = config || {};
    if (this._inner) this._inner.setConfig(this._config);
  }

  set hass(hass) {
    this._hass = hass;
    if (this._inner) this._inner.hass = hass;
    else if (this.isConnected && !this._failed) this._load();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this.style.display = "block";
    this._failed = false;
    this._load();
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

  // Import the Family script once, then make the real card inside this one.
  _load() {
    if (this._inner || this._pending) return this._pending;
    this._pending = loadPanel()
      .then(() => customElements.whenDefined(VIEW))
      .then(() => {
        const card = document.createElement(VIEW);
        card.setConfig(this._config);
        if (this._hass) card.hass = this._hass;
        this._inner = card;
        this.replaceChildren(card);
      })
      .catch((err) => {
        this._failed = true;
        this.textContent = `Family couldn't load: ${err && err.message ? err.message : err}`;
      })
      .finally(() => {
        this._pending = null;
      });
    return this._pending;
  }
}

if (!customElements.get("family-card")) {
  customElements.define("family-card", FamilyCardLoader);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "family-card",
    name: "Family",
    description: "Chores, rewards and home controls for a shared screen, for everyone or one family member.",
  });
}
