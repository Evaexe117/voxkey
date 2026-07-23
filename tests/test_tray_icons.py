from __future__ import annotations

from voxkey import state
from voxkey.tray import icons


def test_every_state_resolves_to_an_asset_and_a_tooltip() -> None:
    for value in (
        state.STATE_IDLE,
        state.STATE_RECORDING,
        state.STATE_TRANSCRIBING,
        state.STATE_DONE,
        state.STATE_ERROR,
        state.STATE_OFF,
    ):
        name, tooltip = icons.resolve_icon(value, active=True)
        assert name in {
            icons.ICON_IDLE,
            icons.ICON_RECORDING,
            icons.ICON_DONE,
            icons.ICON_ERROR,
            icons.ICON_OFF,
        }
        assert tooltip  # never empty


def test_recording_is_red_and_transcribing_reuses_idle() -> None:
    rec = icons.resolve_icon(state.STATE_RECORDING, active=True)[0]
    assert rec == icons.ICON_RECORDING
    assert (
        icons.resolve_icon(state.STATE_TRANSCRIBING, active=True)[0] == icons.ICON_IDLE
    )


def test_done_is_green_and_error_is_orange() -> None:
    assert icons.resolve_icon(state.STATE_DONE, active=True)[0] == icons.ICON_DONE
    assert icons.resolve_icon(state.STATE_ERROR, active=True)[0] == icons.ICON_ERROR


def test_an_inactive_daemon_forces_the_off_icon() -> None:
    # Even with a "done" state left on disk, a stopped daemon shows off.
    assert icons.resolve_icon(state.STATE_DONE, active=False)[0] == icons.ICON_OFF


def test_an_unknown_state_falls_back_to_idle() -> None:
    assert icons.resolve_icon("nonsense", active=True)[0] == icons.ICON_IDLE


def test_the_assets_directory_holds_every_icon() -> None:
    directory = icons.assets_dir()
    for name in (
        icons.ICON_OFF,
        icons.ICON_IDLE,
        icons.ICON_RECORDING,
        icons.ICON_DONE,
        icons.ICON_ERROR,
    ):
        assert (directory / f"{name}.svg").is_file()
