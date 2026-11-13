"""The Family dashboard in the sidebar.

One page for everyone, including a shared display that kids tap. Its
**Parents** button switches it to the parent controls: straight away for an
admin, with the parent PIN on any other login. ``/family-parents`` (the
Parents sidebar page before 2.0.0, and where the parents' notifications
link) still opens it, already switched to the parent controls, but isn't in
the sidebar. Only registered when the frontend is running (not in tests).
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration

from .const import DOMAIN

STATIC_URL = f"/{DOMAIN}_static"
FRONTEND_DIR = Path(__file__).parent / "frontend"
COMPONENT = "family-panel"
FAMILY_PATH = "family"
PARENTS_PATH = "family-parents"
DATA_PANELS = f"{DOMAIN}_panels"
DATA_STATIC = f"{DOMAIN}_static"
DATA_CARD = f"{DOMAIN}_card"


async def async_register_panels(hass: HomeAssistant) -> None:
    if hass.data.get(DATA_PANELS):
        return
    if "frontend" not in hass.config.components or hass.http is None:
        return
    from homeassistant.components import panel_custom  # noqa: PLC0415
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    if not hass.data.get(DATA_STATIC):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[DATA_STATIC] = True
    version = (await async_get_integration(hass, DOMAIN)).version
    # The version in the URL makes browsers fetch the new script after an update.
    module_url = f"{STATIC_URL}/family-panel.js?v={version}"
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=FAMILY_PATH,
        webcomponent_name=COMPONENT,
        sidebar_title="Family",
        sidebar_icon="mdi:home-heart",
        module_url=module_url,
        require_admin=False,
        config={"mode": "family"},
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PARENTS_PATH,
        webcomponent_name=COMPONENT,
        # Not in the sidebar: old links and notifications open Family's
        # parent controls (the PIN still applies to logins that aren't admins).
        sidebar_title=None,
        sidebar_icon=None,
        module_url=module_url,
        require_admin=False,
        config={"mode": "parents"},
    )
    # The Family card on any dashboard: a dashboard can be a login's default
    # (a shared screen's), and a sidebar page can't.
    from homeassistant.components import frontend  # noqa: PLC0415

    frontend.add_extra_js_url(hass, module_url)
    hass.data[DATA_CARD] = module_url
    hass.data[DATA_PANELS] = True


@callback
def async_remove_panels(hass: HomeAssistant) -> None:
    if not hass.data.get(DATA_PANELS):
        return
    from homeassistant.components import frontend  # noqa: PLC0415

    for path in (FAMILY_PATH, PARENTS_PATH):
        frontend.async_remove_panel(hass, path, warn_if_unknown=False)
    if url := hass.data.pop(DATA_CARD, None):
        frontend.remove_extra_js_url(hass, url)
    hass.data[DATA_PANELS] = False
