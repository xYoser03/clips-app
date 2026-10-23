#!/usr/bin/env bash
# ==============================================================================
# clipctl - Instalador para CachyOS / Arch Linux
# Idempotente: seguro de ejecutar múltiples veces sin duplicar configuraciones
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
APP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/clipctl"
CLIPS_DIR="$HOME/Videos/Clips"

echo "=========================================================="
echo "      Instalando clipctl (Instant Replay para Hyprland)   "
echo "=========================================================="

# 1. Verificar dependencias esenciales
echo "[1/7] Verificando dependencias del sistema..."
DEPS=("gpu-screen-recorder" "python3" "notify-send" "hyprctl")
MISSING_DEPS=()

for dep in "${DEPS[@]}"; do
    if ! command -v "$dep" >/dev/null 2>&1; then
        MISSING_DEPS+=("$dep")
    fi
done

# Verificar PyGObject (GTK4)
if ! python3 -c "import gi; gi.require_version('Gtk', '4.0')" >/dev/null 2>&1; then
    MISSING_DEPS+=("python-gobject" "gtk4")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "Faltan las siguientes dependencias: ${MISSING_DEPS[*]}"
    echo "Instalando dependencias faltantes..."
    if command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --needed --noconfirm "${MISSING_DEPS[@]}" || {
            echo "Aviso: Si alguna dependencia está en AUR (como gpu-screen-recorder), instálala con paru o yay."
        }
    fi
else
    echo "✓ Todas las dependencias están satisfechas."
fi

# 2. Verificar permisos KMS de gsr-kms-server
echo "[2/7] Verificando permisos KMS (DMA-BUF zero-copy)..."
if command -v gsr-kms-server >/dev/null 2>&1; then
    KMS_PATH=$(which gsr-kms-server)
    if getcap "$KMS_PATH" 2>/dev/null | grep -q "cap_sys_admin"; then
        echo "✓ gsr-kms-server tiene cap_sys_admin=ep configurado correctamente."
    else
        echo "Configurando cap_sys_admin en $KMS_PATH..."
        sudo setcap cap_sys_admin+ep "$KMS_PATH" || echo "Advertencia: no se pudo configurar setcap; la captura por KMS podría requerir permisos adicionales."
    fi
fi

# 3. Crear directorios necesarios
echo "[3/7] Creando directorios locales..."
mkdir -p "$BIN_DIR" "$SYSTEMD_USER_DIR" "$APP_DIR" "$CONFIG_DIR" "$CLIPS_DIR" "$HOME/.config/autostart"

# 4. Instalar binarios y scripts en ~/.local/bin
echo "[4/7] Instalando ejecutables en $BIN_DIR..."
ln -sf "$SCRIPT_DIR/bin/clipctl" "$BIN_DIR/clipctl"
ln -sf "$SCRIPT_DIR/scripts/waybar-module.sh" "$BIN_DIR/clipctl-waybar"
chmod +x "$BIN_DIR/clipctl" "$BIN_DIR/clipctl-waybar"

# 5. Instalar y habilitar servicio systemd --user
echo "[5/7] Configurando servicio systemd para inicio automático..."
ln -sf "$SCRIPT_DIR/systemd/clipctl.service" "$SYSTEMD_USER_DIR/clipctl.service"
systemctl --user daemon-reload
systemctl --user enable clipctl.service
systemctl --user restart clipctl.service

# 6. Instalar lanzadores y autostart del icono en la bandeja
echo "[6/7] Instalando accesos directos y autostart del icono de bandeja..."
cp -f "$SCRIPT_DIR/desktop/"*.desktop "$APP_DIR/"
chmod +x "$APP_DIR"/clipctl*.desktop
cp -f "$SCRIPT_DIR/desktop/clipctl-tray.desktop" "$HOME/.config/autostart/clipctl-tray.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

# Iniciar icono en la bandeja si no está corriendo
if ! pgrep -f "clipctl tray" >/dev/null 2>&1; then
    nohup clipctl tray >/dev/null 2>&1 &
fi

# 7. Configurar atajos y reglas en Hyprland
echo "[7/7] Configurando atajo global en Hyprland..."
python3 "$SCRIPT_DIR/src/hyprland.py" "SUPER + F10"

echo ""
echo "=========================================================="
echo "             ¡Instalación completada con éxito!           "
echo "=========================================================="
echo " - Atajo global configurado: SUPER + F10 (guarda el buffer actual)"
echo " - Menú de configuración: 'clipctl gui' o desde tu lanzador de apps"
echo " - Servicio activo en segundo plano: systemd --user status clipctl.service"
echo " - Destino de clips: $CLIPS_DIR"
echo "=========================================================="
clipctl status || true
