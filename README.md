# clipctl — Instant Replay Ultraligero para Hyprland y NVIDIA (NVENC)

Sistema de repeticiones instantáneas retroactivas (*Instant Replay* / *ShadowPlay*) diseñado específicamente para **CachyOS / Arch Linux**, **Hyprland** (Wayland) y tarjetas gráficas **NVIDIA** con encoder por hardware **NVENC**.

---

## 🚀 Características Principales

- **Buffer Circular Continuo**: Graba en memoria RAM (o disco NVMe) los últimos N minutos sin escribir continuamente a tu disco SSD.
- **Guardado Instantáneo sin Re-encoding (Remux)**: Escribe el archivo final en **menos de 200 ms** copiando el stream ya codificado por hardware, sin pérdida de calidad ni retrasos.
- **Captura KMS / DMA-BUF Zero-Copy**: Captura de pantalla completa por hardware mediante `gsr-kms-server` (evita copias pesadas por CPU).
- **Atajo Global a Prueba de Juegos (`bindp` / `locked`)**: Funciona en juegos a pantalla completa (Steam, Proton, Wine) aunque el juego capture o intente inhibir atajos globales.
- **Audio Multicanal Separado**: Graba el audio del juego/sistema en la Pista 1 y tu micrófono en la Pista 2 independiente (ideal para edición en DaVinci Resolve o Kdenlive).
- **Consumo Mínimo de Recursos**:
  - CPU total del sistema: **~1.1%**.
  - Encoder hardware NVENC: dedicado, sin afectar los núcleos CUDA del juego ni tus FPS.
  - Daemon orientado a eventos (socket Unix / señales POSIX): **0% CPU** en espera.
- **Interfaz Gráfica GTK4 Bajo Demanda**: Se abre únicamente cuando la invocas y se cierra completamente sin dejar procesos residentes ni consumir memoria.
- **Notificaciones Nativas**: Aviso mediante `notify-send` con ruta del clip y sonido corto de obturador (`pw-play` / `paplay`).
- **Módulo para Waybar**: Script listo para mostrar el estado en tu barra.

---

## 📋 Requisitos del Sistema

- **GPU**: NVIDIA con driver propietario (versión 535+ recomendada; probado en 610+).
- **Compositor**: Hyprland (0.50+).
- **Servidor de Audio**: PipeWire con compatibilidad PulseAudio.
- **Paquetes**: `gpu-screen-recorder`, `python`, `python-gobject`, `gtk4`, `libnotify`.

---

## 📥 Instalación Rápida

Clona o descarga el proyecto y ejecuta el instalador automatizado e idempotente:

```bash
cd ~/clipctl
./install.sh
```

El script se encargará de:
1. Verificar e instalar dependencias faltantes.
2. Comprobar permisos `cap_sys_admin` en `gsr-kms-server`.
3. Instalar `clipctl` en `~/.local/bin/clipctl`.
4. Configurar e iniciar el servicio `systemd --user clipctl.service`.
5. Instalar la integración en Hyprland (`~/.config/hypr/clipctl.lua` y `clipctl.conf`).
6. Instalar el acceso directo de escritorio (`clipctl-gui.desktop`).

### Desinstalación Limpia

```bash
./uninstall.sh
```

---

## 🎮 Uso Diario

### 1. Atajos de Teclado en Hyprland
- **`SUPER + F10`**: Guardar instantáneamente los últimos minutos (por defecto 2 min).
- **`SUPER + ALT + F10`**: Abrir el **Menú Rápido** emergente (vía Fuzzel / dmenu) para guardar duraciones específicas (30s, 1m, 2m, 5m), pausar el buffer o abrir la GUI.

### 2. Comandos CLI (`clipctl`)

```bash
# Abrir el Menú Rápido interactivo (Fuzzel / dmenu / Terminal)
clipctl menu

# Guardar el buffer configurado (por ejemplo los últimos 2 minutos)
clipctl save

# Guardar una duración específica en segundos (ej. los últimos 30 segundos)
clipctl save 30

# Ver el estado actual del buffer, monitor, encoder y consumo de RAM
clipctl status

# Ver estado en formato JSON (para scripts y barras)
clipctl status --json

# Iniciar o detener la grabación manualmente
clipctl start
clipctl stop

# Reiniciar la grabación aplicando nueva configuración
clipctl restart

# Ver o editar la configuración en TOML
clipctl config
clipctl config video.fps 120

# Abrir el panel de configuración gráfico completo (GTK4)
clipctl gui
```

### 3. Entradas en el Menú de Aplicaciones (Lanzadores)
En tu lanzador de aplicaciones (Fuzzel, Rofi, Wofi o Caelestia) encontrarás:
- **`clipctl (Menú Rápido)`**: Lanza el menú emergente de acciones rápidas.
- **`clipctl (Configuración)`** o **`clipctl - Instant Replay`**: Abre la ventana de configuración completa GTK4.

---

## ⚙️ Configuración (`~/.config/clipctl/config.toml`)

La configuración es persistente y puede editarse desde la GUI o directamente en el archivo TOML:

```toml
[video]
monitor = "DP-2"              # Nombre del monitor (DP-2, HDMI-A-1) o "portal"
resolution = "1920x1080"
fps = 60                      # 30, 60, 120, 180
codec = "h264"                # h264, hevc (H.265), av1 (RTX serie 40+)
bitrate = 30000               # Bitrate en kbps (30 Mbps recomendado para 1080p60)
bitrate_mode = "cbr"          # "cbr" para memoria predecible en RAM, o "vbr"
tune = "performance"          # "performance" o "quality"

[replay]
buffer_seconds = 120          # Duración del búfer circular continuo en segundos
default_save_seconds = 120    # Duración por defecto al presionar el atajo
storage = "ram"               # "ram" (sin desgaste SSD) o "disk" (NVMe)
restart_on_save = false       # Vaciar buffer tras guardar (false mantiene el buffer)

[audio]
record_desktop = true         # Audio del juego y escritorio (Pista 1)
desktop_device = "default_output"
record_mic = false            # Micrófono (Pista 2 separada)
mic_device = "default_input"
codec = "opus"

[output]
directory = "/home/yoserad/Videos/Clips"
prefix = "Clip_"              # Formato: Clip_YYYY-MM-DD_HH-MM-SS.mp4

[notifications]
enabled = true                # Notificación con notify-send
sound = true                  # Sonido de disparo de cámara al guardar
sound_file = "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga"

[hyprland]
keybind = "SUPER + F10"
```

---

## 🖥️ Integración con Hyprland

### Hyprland con Configuración Lua (Caelestia / CachyOS)
El sistema genera `~/.config/hypr/clipctl.lua`:
```lua
hl.bind("SUPER + F10", hl.dsp.exec_cmd("clipctl save"), { locked = true })
hl.window_rule({ match = { app_id = "clipctl-gui" }, float = true, center = true })
```
Se incluye automáticamente en `~/.config/caelestia/hypr-user.lua`.

### Hyprland Clásico (`hyprland.conf`)
Se genera `~/.config/hypr/clipctl.conf`:
```ini
bindp = SUPER, F10, exec, clipctl save
windowrulev2 = float, class:^(clipctl-gui)$
windowrulev2 = center, class:^(clipctl-gui)$
```

> **¿Por qué `bindp` y `locked = true`?**
> En Wayland, muchos juegos y aplicaciones mediante Proton/Wine solicitan inhibir atajos del compositor para capturar el teclado. El flag `p` (`bindp`) de Hyprland indica al compositor que este atajo ignora la inhibición del juego y se ejecuta siempre. El flag `locked` permite que funcione incluso si la sesión se bloquea.

---

## 📊 Módulo para Waybar

Añade este bloque a tu archivo `~/.config/waybar/config`:

```json
"custom/clipctl": {
    "exec": "~/.local/bin/clipctl-waybar",
    "return-type": "json",
    "interval": 3,
    "on-click": "clipctl gui",
    "on-click-right": "clipctl save"
}
```

Y en tu `style.css`:
```css
#custom-clipctl.recording {
    color: #a6da95;
    font-weight: bold;
}
#custom-clipctl.stopped {
    color: #6e738d;
}
```

---

## 📈 Rendimiento y Mediciones en CachyOS (RTX 4060)

Resultados reales medidos con `scripts/benchmark.sh`:

| Métrica | Medición con `clipctl` | Impacto en Juegos |
|---|---|---|
| **CPU del Sistema en Reposo** | **~1.1%** (14% de 1 hilo en CPU de 12 hilos) | Nulo / Imperceptible |
| **Memoria RAM (Buffer de 2 min)** | **~477 MB** | Seguro en sistemas con 16GB+ |
| **Latencia de Guardado de Clip** | **0.136 s (136 milisegundos)** | Instantáneo |
| **GPU Core Utilization** | **~3%** (solo composición KMS) | Sin pérdida de FPS |
| **NVENC Hardware Utilization** | **~24%** (motor independiente) | No compite con shaders |
| **Temperatura GPU en Reposo** | **49 °C** | Idéntica a reposo normal |

### Consideraciones sobre NVIDIA y Estados de Energía (P-States)
- En configuraciones con múltiples monitores o tasas de refresco altas (como DP-2 a 180 Hz + HDMI a 60 Hz), el driver NVIDIA suele mantener la GPU en estado **P0**.
- El encoder NVENC corre en un bloque de silicio independiente de los núcleos CUDA / gráficos 3D. Mantener la grabación activa en segundo plano no aumenta la temperatura ni compite con el rendimiento gráfico del juego.

---

## 🔧 Solución de Problemas

### 1. Error de permisos en captura KMS (`gsr-kms-server`)
Si la captura por KMS falla, asegúrate de que el binario del servidor tenga los permisos adecuados:
```bash
sudo setcap cap_sys_admin+ep /usr/bin/gsr-kms-server
```

### 2. Atajos no responden en Hyprland
Verifica que Hyprland recargue la configuración:
```bash
hyprctl reload
```
Si utilizas el modo alternativo con `evdev`, asegúrate de que tu usuario pertenezca al grupo `input`:
```bash
groups | grep input || sudo usermod -aG input $USER
```

### 3. Audio de juego o micrófono no se escucha
Lista las fuentes de audio disponibles con:
```bash
gpu-screen-recorder --list-audio-devices
```
Comprueba que en `~/.config/clipctl/config.toml` `desktop_device` coincida con tu salida de audio activa de PipeWire (por defecto `default_output`).

---

## 📄 Licencia y Créditos
- Licencia: MIT.
- Motor de captura: [gpu-screen-recorder](https://git.dec05eba.com/gpu-screen-recorder/) por dec05eba.
