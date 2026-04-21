# Wispr Local

Local offline dictation: hold a hotkey to record, Whisper transcribes on-device, text is typed into the focused app. Tauri + React UI, Python (FastAPI + faster-whisper) backend.

**Run**

1. `pip install -r requirements.txt` then `python -m wispr_local.server` (default API: `http://127.0.0.1:8001`; optional `WISPR_PORT`)
2. `npm install` then `npm run tauri dev`

Requires Python 3.10+, Node.js, Rust (for Tauri), and microphone access.
