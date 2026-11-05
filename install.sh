#!/bin/sh
# Link romklang into ~/.local and install its user service. Run from the repo.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user" "$HOME/.local/share/applications"
ln -sfn "$here/romklang" "$HOME/.local/bin/romklang"
ln -sfn "$here/systemd/romklang.service" "$HOME/.config/systemd/user/romklang.service"
ln -sfn "$here/romklang.desktop" "$HOME/.local/share/applications/romklang.desktop"
systemctl --user daemon-reload
echo "Installed. Next: romklang import <HeSuVi folder>, then romklang setup --output <device>."
