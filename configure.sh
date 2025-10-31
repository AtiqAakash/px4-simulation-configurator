cat > ~/Music/Beagle\ Simulator/configure.sh <<'EOF'
#!/usr/bin/env bash
# configure.sh — creates a double-clickable Desktop launcher for Sim

APP_NAME="Sim"
SIM_DIR="/home/atiq/Music/Beagle Simulator"
SIM_PY="$SIM_DIR/sim.py"
ICON_PNG="$SIM_DIR/beagle-sim-256.png"
DESKTOP_FILE="$HOME/Desktop/${APP_NAME}.desktop"

echo "Creating Desktop launcher for $APP_NAME..."

# Create the .desktop file
cat > "$DESKTOP_FILE" <<LAUNCH
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Run the simulator (no terminal)
Exec=/usr/bin/env bash -lc 'cd "$SIM_DIR" && export PX4_NO_PXH=1 NO_PXH=1 LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=offscreen HEADLESS=1 && exec python3 ./sim.py'
Icon=$ICON_PNG
Terminal=false
Categories=Utility;
StartupNotify=false
LAUNCH

# Make it executable and trusted
chmod +x "$DESKTOP_FILE"
gio set "$DESKTOP_FILE" "metadata::trusted" yes 2>/dev/null || true
nautilus -q 2>/dev/null || true

echo "✓ Launcher created at $DESKTOP_FILE"
echo "Double-click the Sim icon on Desktop to start the simulator."
EOF

