"""Shared fixtures."""

from pathlib import Path

import pytest

from custom_components.family import photos


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load Family from custom_components in every test."""
    return


@pytest.fixture(autouse=True)
def own_photo_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test keeps chore photos in its own folder.

    Home Assistant's test harness gives every test the same config folder
    (inside the installed harness), so with ``pytest -n`` one test's photo
    prune or undo could remove the files another test was reading (the
    flaky FileNotFoundError in ``test_gift_ideas``).
    """
    folder = tmp_path / photos.FOLDER
    monkeypatch.setattr(photos.Photos, "folder", property(lambda _self: folder))
    return folder
