# RunPod Deployment Guide

## Problem: RunPod utyka na "pending" po releasach

### Przyczyny:
1. **Brak automatycznego budowania obrazu Docker** - poprzednio obraz musiał być budowany ręcznie
2. **RunPod Template używa starej wersji obrazu** - template ma hardcoded tag
3. **Brak synchronizacji między release a obrazem Docker**

## Rozwiązanie

### 1. Automatyczne Budowanie Obrazu (✅ Już dodane)

Workflow `.github/workflows/docker-publish.yml` automatycznie:
- Buduje obraz Docker przy każdym release
- Pushuje do GitHub Container Registry (ghcr.io)
- Taguje z wersją (np. `v0.1.8`, `0.1.8`, `0.1`, `latest`)

### 2. Konfiguracja RunPod Template

#### A) Dla RunPod Serverless:

1. Zaloguj się do [RunPod Console](https://console.runpod.io)
2. Przejdź do **Serverless → Templates**
3. Edytuj swój template dla `reeltoolkit-renderer`
4. Zmień **Container Image** na:
   ```
   ghcr.io/usy-pawel/reeltoolkit-renderer:latest
   ```
   Lub użyj konkretnej wersji:
   ```
   ghcr.io/usy-pawel/reeltoolkit-renderer:0.1.8
   ```

5. Ustaw **Container Start Command**:
   ```bash
   python3 handler.py
   ```

6. Zmienne środowiskowe:
   ```
   RENDER_AUTH_TOKEN=<your-secret-token>
   MAX_INLINE_BYTES=26214400
   RENDER_MAX_WORKERS=16
   RENDER_TEMP_ROOT=/runpod-volume
   ```

7. Ustaw **Container Disk** na minimum 20GB (dla FFmpeg i temp files)

8. **GPU Configuration**:
   - GPU Type: NVIDIA (dowolna z CUDA support)
   - GPU Count: 1
   - Enable CUDA: ✅

#### B) Dla RunPod Pods (HTTP Service):

1. Zaloguj się do [RunPod Console](https://console.runpod.io)
2. Przejdź do **Pods**
3. Edytuj pod lub utwórz nowy z template
4. **Container Image**:
   ```
   ghcr.io/usy-pawel/reeltoolkit-renderer:latest
   ```

5. **Docker Command** (zostaw domyślne lub):
   ```bash
   uvicorn renderer_service.app:app --host 0.0.0.0 --port 8080
   ```

6. **Exposed Ports**: `8080`

7. **Environment Variables**:
   ```
   RENDER_AUTH_TOKEN=<your-secret-token>
   RENDER_MAX_WORKERS=16
   RENDER_TEMP_ROOT=/workspace
   ```

8. **Volume Mounts** (opcjonalne):
   ```
   /workspace -> dla temporary files
   ```

### 3. Weryfikacja Obrazu

Po każdym release sprawdź czy obraz został zbudowany:

```bash
# Sprawdź dostępne tagi
gh api /users/usy-pawel/packages/container/reeltoolkit-renderer/versions

# Lub przez przeglądarkę:
# https://github.com/usy-pawel/reeltoolkit-renderer/pkgs/container/reeltoolkit-renderer
```

### 4. Testowanie Lokalnie

Przed deploymentem na RunPod, przetestuj obraz lokalnie:

#### Test HTTP Service:
```bash
docker run --rm -it \
  --gpus all \
  -p 8080:8080 \
  -e RENDER_AUTH_TOKEN=test-token \
  ghcr.io/usy-pawel/reeltoolkit-renderer:latest

# Test endpoint
curl http://localhost:8080/health
```

#### Test Serverless Handler:
```bash
docker run --rm -it \
  --gpus all \
  -e RENDER_AUTH_TOKEN=test-token \
  ghcr.io/usy-pawel/reeltoolkit-renderer:latest \
  python3 handler.py
```

### 5. Proces Release (Automatyczny)

Od teraz każdy release automatycznie:

1. **Tworzysz tag i release** (jak przed chwilą):
   ```bash
   # Bump version in pyproject.toml
   git add pyproject.toml
   git commit -m "Bump version to 0.1.9"
   git tag v0.1.9
   git push origin main --tags
   gh release create v0.1.9 --generate-notes
   ```

2. **GitHub Actions automatycznie**:
   - ✅ Buduje obraz Docker
   - ✅ Pushuje do ghcr.io z tagami: `v0.1.9`, `0.1.9`, `0.1`, `latest`
   - ✅ Cache dla szybszych kolejnych buildów

3. **RunPod automatycznie**:
   - Jeśli używasz `:latest` → automatycznie użyje nowego obrazu przy następnym cold start
   - Jeśli używasz `:0.1` → automatycznie użyje najnowszej wersji patch
   - Jeśli używasz `:0.1.9` → musisz ręcznie zaktualizować template

### 6. Monitoring i Debugging

#### Sprawdź logi GitHub Actions:
```bash
# Zobacz status ostatniego workflow
gh run list --workflow=docker-publish.yml

# Zobacz logi konkretnego workflow
gh run view <run-id> --log
```

#### Sprawdź logi RunPod:
1. Console → Serverless → Endpoints → Twój endpoint
2. Kliknij "Logs"
3. Szukaj błędów:
   - `failed to pull image` → obraz nie istnieje lub brak uprawnień
   - `pending` → czeka na GPU lub obraz się ściąga
   - `connection timeout` → networking issue

### 7. Rozwiązywanie Problemów "Pending"

Jeśli nadal utyka na pending:

**A) Upewnij się że obraz jest publiczny:**
1. Idź do: https://github.com/usy-pawel/reeltoolkit-renderer/pkgs/container/reeltoolkit-renderer
2. Package settings → Danger Zone → Change visibility → Public

**B) Sprawdź czy RunPod ma dostęp do obrazu:**
```bash
# Z poziomu RunPod pod (przez SSH lub terminal):
docker pull ghcr.io/usy-pawel/reeltoolkit-renderer:latest
```

**C) Zmniejsz rozmiar obrazu** (jeśli ściąganie trwa długo):
- Obecny obraz jest duży (~3-5GB) przez FFmpeg z CUDA
- To normalne dla GPU workloads
- RunPod cache obraz po pierwszym użyciu

**D) Zwiększ timeout w RunPod:**
- Serverless → Template → Advanced → Container Startup Timeout: `300s`

**E) Sprawdź resource limits:**
- Czy masz wystarczający GPU quota na RunPod?
- Czy wybrane GPU są dostępne?

### 8. Uprawnienia GitHub Container Registry

Jeśli GitHub Actions nie może pushować obrazu:

1. Ustawienia repo → Actions → General → Workflow permissions
2. Wybierz: **Read and write permissions**
3. Zaznacz: **Allow GitHub Actions to create and approve pull requests**

### 9. Pull Image Przed Deploymentem

Możesz ręcznie pre-pull obraz na RunPod:

```bash
# Z poziomu RunPod terminal:
docker pull ghcr.io/usy-pawel/reeltoolkit-renderer:latest

# Verify FFmpeg+NVENC:
docker run --rm --gpus all ghcr.io/usy-pawel/reeltoolkit-renderer:latest \
  ffmpeg -hide_banner -encoders | grep nvenc
```

## Podsumowanie Zmian

✅ **Przed**: Ręczne budowanie i pushowanie obrazu → RunPod czeka na nieistniejący obraz
✅ **Po**: Automatyczne budowanie przy każdym release → RunPod zawsze ma aktualny obraz

### Kolejne kroki:

1. ✅ Workflow Docker został dodany
2. ⏳ Push zmian na GitHub
3. ⏳ Trigger pierwszego buildu (można ręcznie przez Actions)
4. ⏳ Zaktualizuj RunPod Template do używania ghcr.io obrazu
5. ⏳ Ustaw obraz jako publiczny
6. ✅ Ciesz się automatycznymi deploymentami! 🎉
