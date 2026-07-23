#!/usr/bin/env bash
# Install voxkey's desktop integration: the systemd user units the tray toggles,
# the application and autostart entries, and the checks pip cannot do.
#
# voxkey itself is installed separately, ideally with `pipx install voxkey[gui]`.
# This script only wires it into the desktop session.
set -euo pipefail

systemd_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
applications_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
autostart_dir="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing systemd user units into $systemd_dir"
mkdir -p "$systemd_dir"
cp "$here/systemd/voxkey.service" "$here/systemd/voxkey-ptt.service" "$systemd_dir/"
systemctl --user daemon-reload

echo "Installing desktop entries"
mkdir -p "$applications_dir" "$autostart_dir"
cp "$here/voxkey.desktop" "$applications_dir/"
cp "$here/voxkey-tray.desktop" "$autostart_dir/"

# Stop dictate so the two never fight over the microphone or the key.
for unit in dictate-ptt dictate; do
    if systemctl --user --quiet is-active "$unit" 2>/dev/null; then
        echo "Stopping and disabling $unit (voxkey replaces it)"
        systemctl --user stop "$unit" || true
        systemctl --user disable "$unit" 2>/dev/null || true
    fi
done

# The push-to-talk client reads /dev/input, which needs the input group.
if ! id -nG | tr ' ' '\n' | grep -qx input; then
    echo
    echo "You are not in the 'input' group, which reading the keyboard needs."
    echo "Run:  sudo usermod -aG input \"$USER\"   then log out and back in."
fi

# GTK and the AppIndicator are system libraries, not pip packages.
if ! python3 -c 'import gi; gi.require_version("Gtk","3.0"); gi.require_version("AyatanaAppIndicator3","0.1")' 2>/dev/null; then
    echo
    echo "GTK 3 or AyatanaAppIndicator3 is missing. On Debian/Ubuntu/Mint:"
    echo "  sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1"
fi

echo
echo "Done. Turn dictation on from the tray icon, or run: voxkey tray"
