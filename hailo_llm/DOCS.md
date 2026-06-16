# Hailo LLM Documentation

## What's new in 2.0
- Models are now **persistently stored** under `/data` inside the addon. Downloaded models survive `ha addon restart` and full HAOS reboots.
- A full **modern interactive chat UI** (OpenWebUI-inspired) is served at the ingress root (`/`).
  - Sidebar with persistent chat history (new chat, rename, delete, switch).
  - Model selector + "Models" manager.
  - Curated one-click downloads for recommended Hailo-optimized models + free-text pull with live progress.
  - Streaming chat, regenerate, copy, edit user messages, stop generation.
  - System prompt + basic generation parameters supported via the chat API.
- The service remains a first-class **Ollama-compatible backend** (the Python layer proxies `/api/*` and `/hailo/*` transparently).

## Options
- `keep_alive` — passed to the backend as `OLLAMA_KEEP_ALIVE`.
- `auto_download_model` — if true, the addon will automatically pull a recommended default model the first time it starts with no models present.

## Accessing the UI
- Use the **Hailo LLM** panel in Home Assistant (or open the ingress URL).
- The UI works great inside the Lovelace panel.

## API (Ollama compatible)
- The same port (8000) that serves the web UI also exposes the full Ollama-compatible surface via a lightweight proxy:
  - `GET /api/tags`
  - `POST /api/pull` (with `stream: true` for progress)
  - `POST /api/chat` (with `stream: true`)
  - `DELETE /api/delete`, etc.
- External consumers (Home Assistant conversation integrations, curl, Open WebUI pointing at the addon, etc.) can continue to use the ingress URL or the mapped host port exactly as before.

## Persistence guarantees
- Everything under `/data` (models + chat JSON history) is durable on HAOS.
- You can safely restart or reboot — your downloaded models and conversations will still be there.

## Tips
- First model pull can take a while (depends on model size and your internet connection).
- The curated models in the UI are chosen from the official Hailo GenAI Model Zoo for best compatibility/performance on the Hailo-10H.
- You can still pull any model the backend supports by typing the exact tag.