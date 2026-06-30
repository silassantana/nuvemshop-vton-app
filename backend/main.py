"""
VTON backend proxy + static file server.
- POST /api/tryon  — proxies to Replicate, keeps token server-side
- GET  /widget/*   — serves the try-on widget (tryon-widget/)
- GET  /app/*      — serves the NubeSDK bundle (dist/)
Deploy on Railway; set REPLICATE_API_TOKEN env var.
"""

import os
from pathlib import Path

import base64
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent.parent  # repo root

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to Nuvemshop store origins before production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
REPLICATE_MODEL_VERSION = os.environ.get(
    "REPLICATE_MODEL_VERSION",
    "a10ae1ae726e5050a961e056e65cb84a576f308528c50993a6d3800d1a2ec162",
)
REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"


def to_data_uri(data: bytes, content_type: str) -> str:
    b64 = base64.b64encode(data).decode()
    return f"data:{content_type};base64,{b64}"


@app.post("/api/tryon")
async def tryon(
    person_image: UploadFile = File(...),
    garment_url: str = Form(...),
    category: str = Form("tops"),
):
    person_bytes = await person_image.read()
    person_uri = to_data_uri(person_bytes, person_image.content_type or "image/jpeg")

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
        "Prefer": "wait",  # synchronous — waits up to 60s
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


@app.get("/health")
def health():
    return {"ok": True}


# Mount static files last so API routes take priority
widget_dir = BASE / "tryon-widget"
dist_dir = BASE / "dist"

if widget_dir.exists():
    app.mount("/widget", StaticFiles(directory=str(widget_dir), html=True), name="widget")

if dist_dir.exists():
    app.mount("/app", StaticFiles(directory=str(dist_dir)), name="app")
