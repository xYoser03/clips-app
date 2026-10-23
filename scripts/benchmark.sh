#!/usr/bin/env bash
# ==============================================================================
# clipctl - Script de Benchmark y Medición de Recursos
# Mide CPU (ps/pidstat), RAM (RSS), GPU y Encoder NVENC (nvidia-smi dmon)
# ==============================================================================

set -euo pipefail

DURATION=10
TMP_DIR="/tmp/clipctl_bench_$$"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "=========================================================="
echo "          clipctl Benchmark - Medición de Rendimiento     "
echo "=========================================================="

# 1. Asegurar que clipctl está activo
if ! clipctl status | grep -q "GRABANDO"; then
    echo "[!] Iniciando buffer de clipctl para el benchmark..."
    clipctl start
    sleep 2
fi

GSR_PID=$(pgrep -f "gpu-screen-recorder.*-r" | head -n 1 || true)
DAEMON_PID=$(pgrep -f "src.daemon|clipctl daemon" | head -n 1 || true)

if [ -z "$GSR_PID" ]; then
    echo "Error: gpu-screen-recorder no encontrado."
    exit 1
fi

echo "Procesos detectados:"
echo " - gpu-screen-recorder PID: $GSR_PID"
echo " - clipctl daemon      PID: ${DAEMON_PID:-N/A}"
echo ""
echo "[1/3] Monitoreando recursos en reposo durante ${DURATION}s..."

# Monitorear CPU y RAM del proceso GSR con ps en bucle
CPU_SAMPLES="$TMP_DIR/cpu_samples.txt"
GPU_SAMPLES="$TMP_DIR/gpu_samples.txt"

for i in $(seq 1 "$DURATION"); do
    ps -p "$GSR_PID" -o %cpu,rss --no-headers >> "$CPU_SAMPLES" 2>/dev/null || true
    nvidia-smi --query-gpu=pstate,utilization.gpu,utilization.encoder,utilization.memory,temperature.gpu,power.draw --format=csv,noheader,nounits >> "$GPU_SAMPLES" 2>/dev/null || true
    sleep 1
done

# Calcular promedios
AVG_CPU=$(awk '{sum+=$1; count++} END {if (count>0) printf "%.2f", sum/count; else print "0"}' "$CPU_SAMPLES")
MAX_RSS_KB=$(awk 'BEGIN{max=0} {if ($2>max) max=$2} END {printf "%.1f", max/1024}' "$CPU_SAMPLES")

AVG_GPU_UTIL=$(awk -F',' '{sum+=$2; count++} END {if (count>0) printf "%.1f", sum/count; else print "0"}' "$GPU_SAMPLES")
AVG_ENC_UTIL=$(awk -F',' '{sum+=$3; count++} END {if (count>0) printf "%.1f", sum/count; else print "0"}' "$GPU_SAMPLES")
AVG_MEM_UTIL=$(awk -F',' '{sum+=$4; count++} END {if (count>0) printf "%.1f", sum/count; else print "0"}' "$GPU_SAMPLES")
LAST_PSTATE=$(tail -n 1 "$GPU_SAMPLES" | cut -d',' -f1 | tr -d ' ')
LAST_TEMP=$(tail -n 1 "$GPU_SAMPLES" | cut -d',' -f5 | tr -d ' ')
LAST_POWER=$(tail -n 1 "$GPU_SAMPLES" | cut -d',' -f6 | tr -d ' ')

echo ""
echo "[2/3] Midiendo latencia de guardado de un clip de 10 segundos..."
START_TS=$(date +%s%N)
SAVE_OUTPUT=$(clipctl save 10)
END_TS=$(date +%s%N)

SAVE_TIME_MS=$(( (END_TS - START_TS) / 1000000 ))
SAVE_TIME_SEC=$(awk -v ms="$SAVE_TIME_MS" 'BEGIN {printf "%.3f", ms/1000}')

CLIP_PATH=$(echo "$SAVE_OUTPUT" | grep -o '/.*\.mp4' | head -n 1)

echo "$SAVE_OUTPUT"
echo "Tiempo de guardado medido: ${SAVE_TIME_SEC} s (${SAVE_TIME_MS} ms)"

echo ""
echo "[3/3] Inspeccionando stream y sincronización de audio..."
if [ -n "$CLIP_PATH" ] && [ -f "$CLIP_PATH" ]; then
    ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,codec_type,channels -of default=noprint_wrappers=1 "$CLIP_PATH" > "$TMP_DIR/probe.txt"
    CLIP_DURATION=$(grep "^duration=" "$TMP_DIR/probe.txt" | cut -d'=' -f2 | cut -d'.' -f1)
    CLIP_SIZE_MB=$(awk -v b="$(grep "^size=" "$TMP_DIR/probe.txt" | cut -d'=' -f2)" 'BEGIN {printf "%.2f", b/(1024*1024)}')
    STREAMS=$(grep "^codec_name=" "$TMP_DIR/probe.txt" | cut -d'=' -f2 | tr '\n' ' ')
fi

echo ""
echo "=========================================================="
echo "               RESUMEN DEL BENCHMARK                      "
echo "=========================================================="
NPROC=$(nproc || echo "1")
TOTAL_CPU=$(awk -v cpu="$AVG_CPU" -v cores="$NPROC" 'BEGIN {printf "%.2f", cpu/cores}')

printf " %-28s : %s\n" "Uso CPU Promedio (GSR)" "${AVG_CPU} % (de 1 hilo / ${TOTAL_CPU}% CPU total)"
printf " %-28s : %s\n" "Memoria RAM (RSS Máx)" "${MAX_RSS_KB} MB"
printf " %-28s : %s\n" "GPU Compute Core Util" "${AVG_GPU_UTIL} %"
printf " %-28s : %s\n" "NVIDIA NVENC Encoder Util" "${AVG_ENC_UTIL} %"
printf " %-28s : %s\n" "GPU VRAM Util" "${AVG_MEM_UTIL} %"
printf " %-28s : %s\n" "Estado P-State GPU" "${LAST_PSTATE}"
printf " %-28s : %s\n" "Temperatura GPU" "${LAST_TEMP} °C"
printf " %-28s : %s\n" "Consumo Potencia GPU" "${LAST_POWER}"
echo "----------------------------------------------------------"
printf " %-28s : %s\n" "Latencia Guardado Clip" "${SAVE_TIME_SEC} s (< 1.0s ideal)"
printf " %-28s : %s\n" "Duración Clip Generado" "${CLIP_DURATION:-N/A} segundos"
printf " %-28s : %s\n" "Tamaño Archivo" "${CLIP_SIZE_MB:-N/A} MB"
printf " %-28s : %s\n" "Streams de Video/Audio" "${STREAMS:-N/A}"
echo "=========================================================="

CPU_OK=$(awk -v c="$TOTAL_CPU" 'BEGIN {print (c < 3.0) ? "1" : "0"}')
if [ "$CPU_OK" = "1" ]; then
    echo "✓ CRITERIO DE ACEPTACIÓN CUMPLIDO: CPU total del sistema en reposo < 3% (${TOTAL_CPU}%)"
else
    echo "⚠ Criterio CPU: ${TOTAL_CPU}% CPU total (${AVG_CPU}% de un hilo)"
fi

SAVE_OK=$(awk -v s="$SAVE_TIME_SEC" 'BEGIN {print (s < 2.0) ? "1" : "0"}')
if [ "$SAVE_OK" = "1" ]; then
    echo "✓ CRITERIO DE ACEPTACIÓN CUMPLIDO: Guardado instantáneo < 2.0s (${SAVE_TIME_SEC}s)"
else
    echo "⚠ Criterio Guardado: ${SAVE_TIME_SEC}s"
fi
echo "=========================================================="
