"""
VTON backend proxy + static file server.

Inference routing (checked in order):
  1. TRYON_ENDPOINT_URL is set  → forward multipart to that URL (Modal, any FastAPI-compatible endpoint)
  2. REPLICATE_API_TOKEN is set → call Replicate synchronous predictions API

Static routes:
  GET /widget/*  → tryon-widget/
  GET /app/*     → dist/  (NubeSDK bundle)

Deploy on Railway; set TRYON_ENDPOINT_URL for Modal or REPLICATE_API_TOKEN for Replicate.
"""

import asyncio
import json
import os
from pathlib import Path

import base64
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent.parent  # repo root

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ── Inference backend config ───────────────────────────────────────────────────

TRYON_ENDPOINT_URL = os.environ.get("TRYON_ENDPOINT_URL")  # e.g. Modal web endpoint

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
REPLICATE_MODEL_VERSION = os.environ.get(
    "REPLICATE_MODEL_VERSION",
    "a10ae1ae726e5050a961e056e65cb84a576f308528c50993a6d3800d1a2ec162",
)
REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"

if not TRYON_ENDPOINT_URL and not REPLICATE_API_TOKEN:
    import warnings
    warnings.warn(
        "Neither TRYON_ENDPOINT_URL nor REPLICATE_API_TOKEN is set — "
        "/api/tryon will return 503 until one is configured."
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def to_data_uri(data: bytes, content_type: str) -> str:
    b64 = base64.b64encode(data).decode()
    return f"data:{content_type};base64,{b64}"


# ── Inference routes ───────────────────────────────────────────────────────────

@app.post("/api/tryon")
async def tryon(
    person_image: UploadFile = File(...),
    garment_url: str = Form(...),
    category: str = Form("tops"),
):
    if not TRYON_ENDPOINT_URL and not REPLICATE_API_TOKEN:
        raise HTTPException(status_code=503, detail="No inference backend configured")

    person_bytes = await person_image.read()
    content_type = person_image.content_type

    async def stream():
        # Immediate event so Railway/nginx doesn't 502 on slow cold starts
        yield f"data: {json.dumps({'status': 'processing'})}\n\n"

        result: dict = {}
        done = asyncio.Event()

        async def run():
            try:
                if TRYON_ENDPOINT_URL:
                    result['ok'] = await _call_modal(person_bytes, content_type, garment_url, category)
                else:
                    result['ok'] = await _call_replicate(person_bytes, content_type, garment_url, category)
            except HTTPException as exc:
                result['error'] = exc.detail
            except Exception as exc:
                result['error'] = str(exc)
            finally:
                done.set()

        asyncio.create_task(run())

        # Keepalive every 5 s while inference runs (resets Railway's 60s timeout)
        while not done.is_set():
            await asyncio.sleep(5)
            if not done.is_set():
                yield f"data: {json.dumps({'status': 'processing'})}\n\n"

        if 'error' in result:
            yield f"data: {json.dumps({'status': 'error', 'detail': result['error']})}\n\n"
        else:
            yield f"data: {json.dumps({'status': 'done', 'result_url': result['ok']['result_url']})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _call_modal(
    person_bytes: bytes,
    content_type: str | None,
    garment_url: str,
    category: str,
) -> dict:
    """Forward multipart to the Modal FastAPI endpoint."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{TRYON_ENDPOINT_URL.rstrip('/')}/api/tryon",
            files={"person_image": (
                "person.jpg",
                person_bytes,
                content_type or "image/jpeg",
            )},
            data={"garment_url": garment_url, "category": category},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Modal error: {resp.text}")

    data = resp.json()
    if "result_url" not in data:
        raise HTTPException(status_code=502, detail="Unexpected response from Modal endpoint")

    return data


async def _call_replicate(
    person_bytes: bytes,
    content_type: str | None,
    garment_url: str,
    category: str,
) -> dict:
    """Call Replicate synchronous predictions API."""
    person_uri = to_data_uri(person_bytes, content_type or "image/jpeg")

    # Fetch garment server-side — avoids CORS issues from the widget
    async with httpx.AsyncClient(timeout=30.0) as client:
        garment_resp = await client.get(garment_url)
        if garment_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch garment image")
        garment_ct = garment_resp.headers.get("content-type", "image/jpeg")
        garment_uri = to_data_uri(garment_resp.content, garment_ct)

    payload = {
        "version": REPLICATE_MODEL_VERSION,
        "input": {
            "person_image": person_uri,
            "garment_image": garment_uri,
            "category": category,
        },
    }

    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(REPLICATE_API_URL, json=payload, headers=headers)

    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Replicate error: {resp.text}")

    data = resp.json()
    if data.get("status") == "failed":
        raise HTTPException(status_code=502, detail=data.get("error", "Inference failed"))

    output = data.get("output")
    if not output:
        raise HTTPException(status_code=502, detail="No output from model")

    result_url = output[0] if isinstance(output, list) else output
    return {"result_url": result_url}


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    backend = "modal" if TRYON_ENDPOINT_URL else ("replicate" if REPLICATE_API_TOKEN else "none")
    return {"ok": True, "backend": backend}


# ── Static files (mount last so API routes take priority) ─────────────────────

widget_dir = BASE / "tryon-widget"
dist_dir = BASE / "dist"

if widget_dir.exists():
    app.mount("/widget", StaticFiles(directory=str(widget_dir), html=True), name="widget")

if dist_dir.exists():
    app.mount("/app", StaticFiles(directory=str(dist_dir)), name="app")
