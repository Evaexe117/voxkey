from __future__ import annotations

from voxkey.audio.devices import DeviceInfo, choose_input_device


def _device(index: int, name: str, inputs: int = 1) -> DeviceInfo:
    return DeviceInfo(index=index, name=name, max_input_channels=inputs)


def test_pipewire_is_preferred_over_default() -> None:
    # The ALSA "default" device does not route a Bluetooth microphone
    # correctly, so the PipeWire device is chosen by name.
    devices = [_device(0, "default"), _device(1, "pipewire")]
    assert choose_input_device(devices) == 1


def test_pipewire_match_is_case_insensitive() -> None:
    assert choose_input_device([_device(0, "default"), _device(3, "PipeWire")]) == 3


def test_first_input_capable_device_when_no_pipewire() -> None:
    devices = [_device(0, "speakers", inputs=0), _device(1, "usb mic")]
    assert choose_input_device(devices) == 1


def test_output_only_devices_are_never_chosen() -> None:
    assert choose_input_device([_device(0, "hdmi out", inputs=0)]) is None


def test_no_devices_at_all_yields_none() -> None:
    assert choose_input_device([]) is None
