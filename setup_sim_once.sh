#!/usr/bin/env bash
# setup_sim_once.sh
# One-time setup: install "Sim" launcher and Desktop icon using local sim.py and PNG icon.
# Usage:
#   ./setup_sim_once.sh                 # auto-detect sim.py and icon in this folder
#   ./setup_sim_once.sh /path/to/sim.py /path/to/icon.png   # optional explicit paths

set -euo pipefail

APP_NAME="Sim"

# --- Resolve paths ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SIM_PY_DEFAULT="$SCRIPT_DIR/sim.py"

# Choose icon: prefer explicit arg2; else pick the best available in current dir
find_icon_in_dir() {
  local d="$1"
  for n in beagle-sim-512.png beagle-sim-256.png beagle-sim-128.png beagle-sim-64.png *.png; do
    if [[ -f "$d/$n" ]]; then
      echo "$d/$n"
      return 0
    fi
  done
  return 1
}

SIM_PY="${1:-$SIM_PY_DEFAULT}"
ICON_PNG="${2:-$(find_icon_in_dir "$SCRIPT_DIR" || true)}"

# --- Checks ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found. Install it and re-run."
  exit 1
fi

if [[ ! -f "$SIM_PY" ]]; then
  echo "[ERROR] sim.py not found at: $SIM_PY"
  echo "       Pass the path explicitly: ./setup_sim_once.sh /full/path/to/sim.py"
  exit 1
fi

if [[ -z "${ICON_PNG:-}" || ! -f "$ICON_PNG" ]]; then
  echo "[WARN] No icon PNG found next to the script. The launcher will use the theme icon."
  ICON_PNG=""
fi

# --- Wrapper executable ---
mkdir -p "$HOME/.local/bin"
WRAP="$HOME/.local/bin/sim"
cat > "$WRAP" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$SIM_PY"
EOF
chmod +x "$WRAP"

# --- Application entry (.desktop in applications) ---
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR"
APP_DESKTOP="$APP_DIR/sim.desktop"

# We'll use theme icon name "sim" for Applications menu (more robust), but also
# install the theme icon if we have a PNG. Desktop shortcut will use absolute path.
ICON_KEY_FOR_APP="sim"
if [[ -n "$ICON_PNG" ]]; then
  ICON_THEME_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
  mkdir -p "$ICON_THEME_DIR"
  cp -f "$ICON_PNG" "$ICON_THEME_DIR/sim.png"
else
  # fallback to a generic icon name if no PNG
  ICON_KEY_FOR_APP="utilities-terminal"
fi

cat > "$APP_DESKTOP" <<EOF
[Desktop Entry]
Name=$APP_NAME
Comment=PX4 SITL Launcher
Exec=$WRAP
Terminal=false
Type=Application
Icon=$ICON_KEY_FOR_APP
Categories=Development;Utility;
StartupWMClass=sim
EOF

# --- Desktop shortcut (.desktop on Desktop) ---
DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$DESKTOP_DIR"
DESKTOP_SHORTCUT="$DESKTOP_DIR/$APP_NAME.desktop"

# For the desktop icon, prefer absolute path to your PNG to force the exact image
ICON_KEY_FOR_DESKTOP="$ICON_KEY_FOR_APP"
if [[ -n "$ICON_PNG" ]]; then
  ICON_KEY_FOR_DESKTOP="$ICON_PNG"
fi

cat > "$DESKTOP_SHORTCUT" <<EOF
[Desktop Entry]
Name=$APP_NAME
Comment=PX4 SITL Launcher
Exec=$WRAP
Terminal=false
Type=Application
Icon=$ICON_KEY_FOR_DESKTOP
Categories=Development;Utility;
StartupWMClass=sim
EOF

chmod +x "$DESKTOP_SHORTCUT" || true

# Mark as trusted (GNOME/Nautilus)
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_SHORTCUT" "metadata::trusted" yes || true
fi

# Refresh icon and desktop databases if available
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" || true
fi
if command -v update-icon-caches >/dev/null 2>&1; then
  update-icon-caches "$HOME/.local/share/icons" || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" || true
fi

# Restart Nautilus to update desktop view (safe; it auto-restarts)
if command -v nautilus >/dev/null 2>&1; then
  nautilus -q || true
fi

echo "[OK] Installed launcher:"
echo "  • Applications entry: $APP_DESKTOP"
echo "  • Desktop shortcut  : $DESKTOP_SHORTCUT"
echo "  • Wrapper           : $WRAP"
if [[ -n "$ICON_PNG" ]]; then
  echo "  • Icon (app menu)   : hicolor theme -> sim.png (copied from $ICON_PNG)"
  echo "  • Icon (desktop)    : $ICON_PNG"
else
  echo "  • Icon              : theme default (no PNG found)"
fi
echo
echo "Double-click the '$APP_NAME' icon on your Desktop to launch."
echo "If it shows 'Untrusted', right-click → 'Allow Launching'."
