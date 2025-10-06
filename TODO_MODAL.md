# TODO - Modal Deployment

## ✅ Co już działa:

### `modal_app_simple.py` - GOTOWE! 🎉
- ✅ FFmpeg rendering (kolorowe video)
- ✅ Deploy w 13 sekund
- ✅ Test zakończony sukcesem (3032 bytes video)
- ✅ HTTP endpoint: https://pawel-2--reeltoolkit-renderer-simple-web.modal.run
- ✅ Funkcje: `test_ffmpeg()`, `render_simple()`

## ⚠️ Do naprawienia:

### `modal_app.py` - Pełny pipeline z MoviePy
**Problem:** Import errors w MoviePy i reel_renderer

**Błędy do rozwiązania:**

1. **MoviePy import structure**
   - Lokalne: `from moviepy import AudioFileClip` nie działa
   - Trzeba: `from moviepy.editor import AudioFileClip`
   - Plik: `reel_renderer/parallel.py` line 17
   - ✅ NAPRAWIONE lokalnie, ale...

2. **Modal mount/cache problem**
   - Modal używa cache dla mounted directories
   - Zmiany w `reel_renderer/*.py` nie są widoczne po redeploy
   - Próbowano: `.add_local_dir()` - nie działa

3. **Async rendering**
   - `render_reel()` w pipeline.py jest `async def`
   - Trzeba wywołać z `asyncio.run()`
   - ✅ NAPRAWIONE w modal_app.py

**Rozwiązania do wypróbowania:**

### Opcja A: Wbuduj reel_renderer do obrazu (zamiast mount)
```python
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install_from_requirements("requirements.txt")
    .copy_local_dir("reel_renderer", "/root/reel_renderer")  # Copy, nie mount
    .run_commands("cd /root && python -c 'import reel_renderer'")  # Test import
)
```

### Opcja B: Package reel_renderer jako wheel
```bash
# Lokalnie
pip install build
python -m build

# W modal_app.py
image = (
    ...
    .pip_install("./dist/reeltoolkit_renderer-0.1.16-py3-none-any.whl")
)
```

### Opcja C: Fix MoviePy dependencies
```python
# W modal_app.py image definition
.pip_install(
    "moviepy==1.0.3",
    "decorator",  # MoviePy dependency
    "proglog",    # MoviePy dependency
    "imageio-ffmpeg==0.4.9"
)
```

### Opcja D: Przepisz rendering na czysty FFmpeg (jak simple version)
- Najszybsze
- Najmniej zależności
- Najprostsza debuggowanie
- Ale: trzeba przepisać logikę z MoviePy na ffmpeg commands

---

## 📋 Następne kroki (priorytet):

### 1. **Przetestuj HTTP endpoint** (5 min)
```bash
curl -X POST https://pawel-2--reeltoolkit-renderer-simple-web.modal.run/render \
  -H "Content-Type: application/json" \
  -d '{"width": 1080, "height": 1920, "duration": 3, "color": "blue"}'
```

### 2. **Rozbuduj simple version** (1-2h)
Dodaj do `modal_app_simple.py`:
- [ ] Wsparcie dla tekstu (drawtext filter w ffmpeg)
- [ ] Wsparcie dla obrazków (overlay)
- [ ] Multiple slides (concat filter)
- [ ] Audio (ffmpeg -i audio.mp3)
- [ ] Transitions (xfade filter)

### 3. **Napraw pełny pipeline** (2-4h)
- [ ] Wybierz opcję A, B, C lub D
- [ ] Przetestuj import reel_renderer
- [ ] Napraw MoviePy dependencies
- [ ] Test pełnego renderowania

### 4. **Dokumentacja** (30 min)
- [ ] Zaktualizuj README.md z instrukcjami Modal
- [ ] Dodaj przykłady wywołań
- [ ] Porównanie: RunPod vs Modal

### 5. **CI/CD** (opcjonalne, 1h)
- [ ] GitHub Action dla auto-deploy na Modal
- [ ] Testy integracyjne
- [ ] Versioning

---

## 🎯 Rekomendacja:

**KRÓTKI TERMIN (teraz):**
Użyj `modal_app_simple.py` dla prostych przypadków.
Rozbuduj go o funkcje FFmpeg (tekst, obrazki, concat).

**DŁUGI TERMIN (później):**
Napraw `modal_app.py` opcją B (package as wheel) - najbardziej clean.

---

## 💡 Szybkie победы:

### Dodaj text rendering do simple version:
```python
@app.function(image=image, timeout=600)
def render_with_text(text: str, width: int = 720, height: int = 1280):
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:d=3:r=25",
        "-vf", f"drawtext=text='{text}':fontsize=60:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
        "-pix_fmt", "yuv420p",
        str(output)
    ]
    # ... rest
```

### Dodaj image overlay:
```python
@app.function(image=image, timeout=600)
def render_with_image(image_b64: str, width: int = 720, height: int = 1280):
    # Decode image_b64 -> save to temp file
    # ffmpeg -i background.mp4 -i overlay.png -filter_complex overlay ...
```

---

## 📊 Status Matrix:

| Feature | simple version | full pipeline | Trudność |
|---------|---------------|---------------|----------|
| Kolorowe tła | ✅ Działa | ⚠️ Broken | - |
| FFmpeg rendering | ✅ Działa | ⚠️ Broken | - |
| Tekst | ❌ TODO | ⚠️ Broken | Łatwe |
| Obrazki | ❌ TODO | ⚠️ Broken | Średnie |
| Multiple slides | ❌ TODO | ⚠️ Broken | Średnie |
| Audio | ❌ TODO | ⚠️ Broken | Średnie |
| Transitions | ❌ TODO | ⚠️ Broken | Trudne |
| MoviePy effects | ❌ N/A | ⚠️ Broken | Bardzo trudne |

---

## 🔗 Użyteczne linki:

- Modal Dashboard: https://modal.com/apps/pawel-2/main/deployed/reeltoolkit-renderer-simple
- FFmpeg drawtext: https://ffmpeg.org/ffmpeg-filters.html#drawtext
- FFmpeg concat: https://trac.ffmpeg.org/wiki/Concatenate
- FFmpeg xfade: https://trac.ffmpeg.org/wiki/Xfade

---

**Ostatnia aktualizacja:** 2025-10-06

**Następny krok:** Przetestuj HTTP endpoint lub rozbuduj simple version o text rendering.
