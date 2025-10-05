"""FastAPI application exposing the render endpoint."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import contextlib
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from reel_renderer import RenderJobSpec, render_reel

from .config import ServiceSettings, get_settings

app = FastAPI(title="ReelToolkit Renderer", version="0.1.0")


def _check_auth(request: Request, settings: ServiceSettings) -> None:
    if not settings.auth_token:
        return
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    provided = auth_header.split(" ", 1)[1].strip()
    if provided != settings.auth_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bearer token")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/render/reel")
async def render_reel_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: str = Form(...),
    bundle: UploadFile = File(...),
    settings: ServiceSettings = Depends(get_settings),
):
    _check_auth(request, settings)

    try:
        spec = RenderJobSpec.model_validate_json(payload)
    except Exception as exc:  # pragma: no cover - depends on user input
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid payload: {exc}") from exc

    temp_root = Path(settings.temp_root or tempfile.gettempdir())
    work_dir = Path(tempfile.mkdtemp(prefix=f"req_{spec.job_id}_", dir=temp_root))
    bundle_path = work_dir / "bundle.zip"
    output_path = work_dir / spec.output_name

    cleanup_registered = False

    try:
        with bundle_path.open("wb") as dst:
            while True:
                chunk = await bundle.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        await bundle.close()

        final_path = await render_reel(
            spec,
            bundle_path,
            output_path,
            max_workers=settings.max_workers,
        )

        final_filename = os.path.basename(spec.output_name)

        def _cleanup(path: Path) -> None:
            with contextlib.suppress(Exception):
                shutil.rmtree(path)

        file_like = final_path.open("rb")
        background_tasks.add_task(file_like.close)
        background_tasks.add_task(_cleanup, work_dir)
        cleanup_registered = True
        response = StreamingResponse(
            file_like,
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename=\"{final_filename}\"",
                "X-Render-Job-Id": spec.job_id,
            },
        )
        return response

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Render failed: {exc}",
        ) from exc
    finally:
        if not cleanup_registered:
            with contextlib.suppress(Exception):
                shutil.rmtree(work_dir)
