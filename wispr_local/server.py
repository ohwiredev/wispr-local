import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .controller_service import WisprLocalService
from .settings_util import WHISPER_MODEL_IDS

app = FastAPI()
# Tauri/Vite UI loads from another origin (e.g. http://localhost:1420); without CORS, fetch() fails in the webview even when uvicorn logs 200.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
service = WisprLocalService(Path("config/settings.json"))

@app.post("/start")
async def start():
    service.start_recording()
    return {"status": "recording"}

@app.post("/stop")
async def stop():
    service.stop_recording_and_process()
    return {"status": "processing"}

@app.get("/status")
async def status():
    return {
        "is_recording": service.is_recording,
        "is_processing": service.is_processing,
        "last_text": service.last_typed_text,
        "model_loading": service.model_loading,
        "model_loading_name": service.model_loading_name,
        "model_loading_error": service.model_loading_error,
        "model_loading_step": service.transcriber.load_step,
        "model_download_current": service.transcriber.download_current,
        "model_download_total": service.transcriber.download_total,
    }

@app.get("/settings")
async def get_settings():
    return service.settings


@app.get("/transcription/models")
async def list_transcription_models():
    return {"models": sorted(WHISPER_MODEL_IDS)}


@app.post("/settings")
async def update_settings(settings: dict):
    try:
        service.update_settings(settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "updated"}

if __name__ == "__main__":
    port = int(os.environ.get("WISPR_PORT", "8001"))
    uvicorn.run(app, host="127.0.0.1", port=port)
