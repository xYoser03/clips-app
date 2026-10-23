#!/usr/bin/env bash
# ==============================================================================
# clipctl - Script de Desinstalación
# ==============================================================================

set -euo pipefail

BIN_DIR="$HOME/.local/bin"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
APP_DIR="$HOME/.local/share/applications"
HYPR_DIR="$HOME/.config/hypr"
CAELESTIA_USER_LUA="$HOME/.config/caelestia/hypr-user.lua"

echo "=========================================================="
echo "               Desinstalando clipctl...                   "
echo "=========================================================="

# 1. Detener y deshabilitar servicio systemd
echo "[1/5] Deteniendo servicio systemd..."
if systemctl --user is-active clipctl.service >/dev/null 2>&1; then
    systemctl --user stop clipctl.service || true
fi
systemctl --user disable clipctl.service 2>/dev/null || true
rm -f "$SYSTEMD_USER_DIR/clipctl.service"
systemctl --user daemon-reload

# 2. Eliminar ejecutables
echo "[2/5] Eliminando ejecutables..."
rm -f "$BIN_DIR/clipctl" "$BIN_DIR/clipctl-waybar"

# 3. Eliminar archivos .desktop y autostart
echo "[3/5] Eliminando lanzadores y autostart..."
rm -f "$APP_DIR"/clipctl*.desktop "$HOME/.config/autostart/clipctl-tray.desktop"
pkill -f "clipctl tray" || true
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

# 4. Limpiar configuración de Hyprland
echo "[4/5] Limpiando integración con Hyprland..."
rm -f "$HYPR_DIR/clipctl.lua" "$HYPR_DIR/clipctl.conf"
if [ -f "$CAELESTIA_USER_LUA" ]; then
    sed -i '/clipctl/d' "$CAELESTIA_USER_LUA" || true
fi
if command -v hyprctl >/dev/null 2>&1; then
    hyprctl reload >/dev/null 2>&1 || true
fi

# 5. Opciones finales
echo "[5/5] Finalizado."
echo "Nota: Tus clips guardados en ~/Videos/Clips y tu configuración en ~/.config/clipctl se han conservado."
echo "Si deseas eliminarlos, ejecuta: rm -rf ~/.config/clipctl"
echo "Desinstalación de clipctl completada."
