#!/usr/bin/env bash
# Waybar custom module for clipctl
# Add to waybar config:
# "custom/clipctl": {
#     "exec": "~/.local/bin/clipctl-waybar",
#     "return-type": "json",
#     "interval": 3,
#     "on-click": "clipctl gui",
#     "on-click-right": "clipctl save"
# }

STATUS_JSON=$(clipctl status --json 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$STATUS_JSON" ]; then
    echo '{"text":"󰕨 Off","tooltip":"clipctl no está corriendo","class":"stopped"}'
    exit 0
fi

STATUS=$(echo "$STATUS_JSON" | grep -o '"status": *"[^"]*"' | head -1 | cut -d'"' -f4)
BUF=$(echo "$STATUS_JSON" | grep -o '"buffer_seconds": *[0-9]*' | head -1 | grep -o '[0-9]*')
RAM=$(echo "$STATUS_JSON" | grep -o '"estimated_ram_mb": *[0-9.]*' | head -1 | cut -d':' -f2 | tr -d ' ')
MON=$(echo "$STATUS_JSON" | grep -o '"monitor": *"[^"]*"' | head -1 | cut -d'"' -f4)

if [ "$STATUS" = "recording" ]; then
    echo "{\"text\":\"󰕧 ${BUF}s\",\"tooltip\":\"clipctl: Grabando en ${MON}\\nBuffer: ${BUF}s (~${RAM}MB RAM)\\nClick Izq: Menú\\nClick Der: Guardar Clip\",\"class\":\"recording\"}"
else
    echo '{"text":"󰕨 Stop","tooltip":"clipctl: Buffer detenido\\nClick para abrir menú","class":"stopped"}'
fi
