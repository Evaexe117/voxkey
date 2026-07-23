from __future__ import annotations

from voxkey import service


def test_start_and_stop_order_daemon_and_client_correctly() -> None:
    # Start the daemon first, stop it last: the client must never outlive it.
    assert service.start_command() == [
        "systemctl",
        "--user",
        "start",
        "voxkey.service",
        "voxkey-ptt.service",
    ]
    assert service.stop_command() == [
        "systemctl",
        "--user",
        "stop",
        "voxkey-ptt.service",
        "voxkey.service",
    ]


def test_restart_orders_the_daemon_first() -> None:
    assert service.restart_command({"voxkey-ptt.service", "voxkey.service"}) == [
        "systemctl",
        "--user",
        "restart",
        "voxkey.service",
        "voxkey-ptt.service",
    ]
    assert service.restart_command({"voxkey.service"}) == [
        "systemctl",
        "--user",
        "restart",
        "voxkey.service",
    ]


def test_restart_of_an_empty_set_is_none() -> None:
    assert service.restart_command(set()) is None


def test_is_active_probes_the_daemon_quietly() -> None:
    assert service.is_active_command() == [
        "systemctl",
        "--user",
        "is-active",
        "--quiet",
        "voxkey.service",
    ]
