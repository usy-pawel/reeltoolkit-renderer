# Modal GPU Rendering z NVIDIA NVENC

## Konfiguracja

Aplikacja Modal została skonfigurowana do **wyłącznego użycia GPU** z NVIDIA NVENC dla maksymalnej wydajności.

## Zmiany w konfiguracji

### 1. Obraz bazowy - NVIDIA CUDA
```python
modal.Image.from_registry(
    "nvidia/cuda:12.2.0-runtime-ubuntu22.04",
    add_python="3.11"
)
```
- ✅ Zawiera sterowniki NVIDIA
- ✅ CUDA toolkit dla GPU
- ✅ Wsparcie dla NVENC

### 2. FFmpeg z NVENC
Używamy statycznego buildu FFmpeg od johnvansickle, który zawiera wsparcie dla:
- ✅ h264_nvenc (NVIDIA GPU encoding)
- ✅ hevc_nvenc (H.265 dla przyszłości)
- ✅ Wszystkie standardowe kodeki

### 3. Alokacja GPU
```python
@app.function(
    gpu=GPU_CONFIG,  # T40, L40 lub L40S
    memory=8192,
    timeout=600
)
```

### 4. Zmienne środowiskowe
```python
os.environ["RENDER_USE_NVENC"] = "1"  # WŁĄCZONE
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"
```

## Typy GPU dostępne na Modal

Ustaw przez zmienną środowiskową `MODAL_RENDER_GPU`:

| GPU | VRAM | Wydajność | Koszt |
|-----|------|-----------|-------|
| **T40** | 24GB | Bardzo dobry | $ |
| **L40** | 24GB | Świetny | $$ |
| **L40S** | 48GB | Najlepszy | $$$ |

**Domyślnie**: T40 (najlepszy stosunek ceny do wydajności)

## Deployment

### Krok 1: Deploy na Modal
```bash
cd c:/workspace/reeltoolkit-renderer
modal deploy modal_app.py
```

### Krok 2: Weryfikacja
Modal automatycznie:
1. Zbuduje obraz z CUDA + FFmpeg
2. Sprawdzi dostępność h264_nvenc
3. Wdroży funkcję z GPU

### Krok 3: Test
```bash
# Test prostego renderu
modal run modal_app.py

# Sprawdź logi
modal app logs reeltoolkit-renderer
```

## Logi - czego szukać

### ✅ Poprawne logi podczas renderu:
```
📦 Received render job: job_xyz
🎮 GPU detected: NVIDIA T40, Driver Version: 535.xx, 24576MiB
🎬 Starting GPU render: 720x1280 @ 25fps
🔧 FFmpeg path: /usr/bin/ffmpeg
🎥 NVENC enabled: 1
✅ h264_nvenc encoder is available
Rendering video with codec: h264_nvenc, preset: p6
✅ Render complete: 2451678 bytes
```

### ❌ Jeśli widzisz błędy:
```
❌ WARNING: h264_nvenc encoder NOT FOUND!
```
→ FFmpeg nie ma NVENC - sprawdź build FFmpeg

```
⚠️ Could not query GPU
```
→ GPU nie zostało przydzielone - sprawdź konfigurację Modal

## Konfiguracja Backend

Ustaw zmienne środowiskowe w backend:

```bash
# .env lub Railway variables
RENDER_SERVICE_PROVIDER=modal
MODAL_RENDER_APP=reeltoolkit-renderer
MODAL_RENDER_FUNCTION=render_reel
MODAL_RENDER_GPU=T40  # lub L40 / L40S
RENDER_SERVICE_TIMEOUT=600
```

## Parametry NVENC

### Obecne ustawienia (w `reel_renderer/video.py`):
```python
codec = "h264_nvenc"
preset = "p6"  # Balance between speed and quality
bitrate = "8M"
```

### Presety NVENC:
- `p1` (fastest) - najszybszy, najniższa jakość
- `p4` (fast) - szybki
- **`p6` (medium)** ← aktualnie używany
- `p7` (slow) - wolniejszy, lepsza jakość

### Możesz zmienić przez zmienne środowiskowe:
```bash
RENDER_NVENC_PRESET=p4  # Szybszy rendering
RENDER_NVENC_BITRATE=12M  # Wyższa jakość
```

## Wydajność GPU vs CPU

| Metryka | CPU (libx264) | GPU (h264_nvenc) |
|---------|---------------|------------------|
| **1080p video (30s)** | ~60-90s | ~10-20s |
| **Quality** | Excellent | Excellent |
| **Koszt** | $ | $$ |
| **Równoległość** | Niska | Wysoka |

**GPU jest 3-5x szybszy!** 🚀

## Troubleshooting

### Problem: "Unknown encoder 'h264_nvenc'"
**Rozwiązanie**: 
1. Sprawdź czy GPU jest włączone w funkcji Modal
2. Zweryfikuj że używamy właściwego buildu FFmpeg
3. Deploy ponownie: `modal deploy modal_app.py`

### Problem: "Broken pipe"
**Rozwiązanie**:
1. Sprawdź logi GPU: czy sterowniki są dostępne?
2. Zwiększ memory: `memory=16384` (16GB)
3. Zwiększ timeout: `timeout=900` (15 min)

### Problem: Render działa ale używa libx264
**Rozwiązanie**:
Sprawdź zmienną `RENDER_USE_NVENC`:
```python
print(os.environ.get("RENDER_USE_NVENC"))  # Musi być "1"
```

## Monitoring kosztów

Modal charged za:
- **GPU time**: gdy funkcja działa z GPU
- **Compute time**: CPU + memory
- **Egress**: transfer danych

### Optymalizacja kosztów:
1. ✅ Używaj T40 zamiast L40S (o ile nie potrzebujesz ekstra mocy)
2. ✅ Optymalizuj timeout - nie płać za bezczynność
3. ✅ Cache assets w bundle - mniej transferu
4. ✅ Batch rendery jeśli możliwe

## Następne kroki

1. ✅ Deploy aplikacji
2. ✅ Przetestuj pojedynczy render
3. ✅ Przetestuj z transitions
4. ✅ Zmierz wydajność i koszty
5. ✅ Dostosuj GPU type jeśli potrzeba

## Komendy przydatne

```bash
# Deploy
modal deploy modal_app.py

# Test lokalny (symulacja)
modal run modal_app.py::main

# Logi live
modal app logs reeltoolkit-renderer --follow

# Lista deployments
modal app list

# Sprawdź koszty
modal app stats reeltoolkit-renderer
```

---

**Status**: 🟢 Ready for GPU rendering with NVENC
