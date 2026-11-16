"""Take the README screenshots from the preview page (sample family only).

    python scripts/panel-preview/shoot.py [out dir] [--mdi DIR]

Serves the repo, opens scripts/panel-preview/index.html in Chromium
(Playwright) and saves docs/images/*.png. The page has no Home Assistant, so
`<ha-icon>` draws nothing; with --mdi pointing at a folder where
`npm install @mdi/js` was run, the icons are drawn from that package.
Fails on page errors and on sideways scrolling.
"""

from __future__ import annotations

import asyncio
import functools
import http.server
from pathlib import Path
import re
import sys
import threading

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
PAGE = "scripts/panel-preview/index.html"

DRAW = """(paths) => {
  const draw = (root) => {
    for (const el of root.querySelectorAll('ha-icon')) {
      const d = paths[el.getAttribute('icon')];
      if (!d) continue;
      el.innerHTML = `<svg viewBox="0 0 24 24" style="width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);fill:currentColor"><path d="${d}"/></svg>`;
      el.style.display = 'inline-flex';
    }
    for (const el of root.querySelectorAll('*')) if (el.shadowRoot) draw(el.shadowRoot);
  };
  draw(document);
}"""

SCROLL_TO = """(el) => {
  el.scrollIntoView({block: 'start'});
  for (let p = el.parentElement; p; p = p.parentElement) {
    if (p.scrollTop) { p.scrollTop -= 72; return; }
  }
  (document.scrollingElement || document.body).scrollBy(0, -72);
}"""

# (file, query, width, height, Parents tab or None, heading to scroll to)
SHOTS = [
    ("family-dashboard.png", "?mode=family", 1280, 800, None, None),
    ("family-chores.png", "?mode=family", 1280, 800, None, "Up for grabs"),
    ("family-phone.png", "?mode=family#me", 390, 844, None, None),
    ("family-dark.png", "?mode=family&theme=dark", 1280, 800, None, None),
    ("parents-to-check.png", "?mode=parents", 1280, 800, "review", "Chores to check"),
    ("parents-chores.png", "?mode=parents", 1280, 800, "chores", "Who does what"),
    ("parents-rewards.png", "?mode=parents", 1280, 800, "rewards", None),
    ("parents-history.png", "?mode=parents", 1280, 800, "history", "Week by week"),
]


def mdi_paths(folder: str | None) -> dict[str, str]:
    """mdi:<name> -> path data from @mdi/js, or nothing."""
    if not folder:
        return {}
    source = Path(folder) / "node_modules" / "@mdi" / "js" / "mdi.js"
    if not source.exists():
        sys.exit(f"{source} not found: run `npm install @mdi/js` in {folder}")
    paths = {}
    for name, data in re.findall(
        r'export (?:var|const) mdi(\w+) ?= ?"([^"]+)"', source.read_text()
    ):
        paths["mdi:" + re.sub(r"(?<!^)(?=[A-Z0-9])", "-", name).lower()] = data
    return paths


def serve() -> int:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


async def main(out: Path, paths: dict[str, str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{serve()}/{PAGE}"
    errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for name, query, width, height, tab, heading in SHOTS:
            page = await browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(base + query)
            await page.wait_for_timeout(1200)
            if tab:
                await (
                    page.locator("family-panel").locator(f"[data-tab='{tab}']").click()
                )
                await page.wait_for_timeout(400)
            if heading:
                title = page.locator("family-panel").locator("h2", has_text=heading)
                # Under the sticky toolbar, not behind it.
                await title.first.evaluate(SCROLL_TO)
                await page.wait_for_timeout(200)
            if paths:
                await page.evaluate(DRAW, paths)
            if await page.evaluate("document.documentElement.scrollWidth > innerWidth"):
                errors.append(f"{name}: scrolls sideways")
            await page.screenshot(path=str(out / name))
            print("saved", out / name)
            await page.close()
        await browser.close()
    if errors:
        sys.exit("\n".join(errors))


if __name__ == "__main__":
    args = sys.argv[1:]
    mdi = None
    if "--mdi" in args:
        at = args.index("--mdi")
        mdi = args[at + 1]
        del args[at : at + 2]
    target = Path(args[0]) if args else ROOT / "docs" / "images"
    asyncio.run(main(target, mdi_paths(mdi)))
