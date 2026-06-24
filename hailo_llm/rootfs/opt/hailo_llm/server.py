#!/usr/bin/env python3
"""
Hailo LLM Add-on - Web UI + API Proxy (Flask)

- Serves a modern, OpenWebUI-inspired interactive chat experience at the HA ingress (port 8000).
- Provides a thin transparent proxy so the full Ollama-compatible surface (/api/*, /hailo/*)
  remains available on the same port for external clients (HA conversation, curl, etc.).
- Persists downloaded HEF models via XDG_DATA_HOME=/media/hailo_llm (hailo-ollama writes blobs to
  /media/hailo_llm/hailo-ollama/models/blob/sha256_<hash> per hailo_model_zoo_genai source).
- Persists chat history server-side under /data/chats (survives reboots).
- Honors auto_download_model on startup.
"""

from flask import Flask, jsonify, request, Response, send_from_directory
import os
import json
import time
import threading
import uuid
from datetime import datetime
import requests

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BACKEND = os.environ.get("HAILO_BACKEND", "http://127.0.0.1:11434")
DATA_DIR = "/data"
CHATS_DIR = os.path.join(DATA_DIR, "chats")
# Actual HEF blobs live under XDG-controlled dir on media (see run.sh).
# This var is used for makedirs (harmless) + health reporting only.
MODELS_DIR = "/media/hailo_llm/hailo-ollama/models/blob"
OPTIONS_PATH = os.path.join(DATA_DIR, "options.json")

os.makedirs(CHATS_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # dev friendly for the embedded UI

# Curated list of known-good models for the Hailo GenAI Model Zoo (5.x) on Hailo-10H.
# These are the ones the binary's /api/pull understands (HEF-backed).
# Users can still type any other tag the backend accepts.
CURATED_MODELS = [
    "qwen2.5:1.5b",
    "qwen2:1.5b",
    "phi3:3.8b",   # if a HEF variant is published for it
]

# -----------------------------------------------------------------------------
# Helpers - Chat persistence (simple, robust, filesystem based)
# -----------------------------------------------------------------------------

def _chat_path(chat_id: str) -> str:
    return os.path.join(CHATS_DIR, f"{chat_id}.json")

def list_chats():
    """Return lightweight list of chats sorted by last update (newest first)."""
    chats = []
    for fname in os.listdir(CHATS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(CHATS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            chats.append({
                "id": data.get("id"),
                "title": data.get("title", "Untitled"),
                "model": data.get("model", ""),
                "updated": data.get("updated", 0),
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            continue
    chats.sort(key=lambda c: c.get("updated", 0), reverse=True)
    print(f"[chats] list_chats -> {len(chats)} entries")
    return chats

def load_chat(chat_id: str):
    path = _chat_path(chat_id)
    if not os.path.exists(path):
        print(f"[chats] load_chat {chat_id} -> not found")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[chats] load_chat {chat_id} -> {len(data.get('messages', []))} msgs")
            return data
    except Exception as e:
        print(f"[chats] load_chat {chat_id} error: {e}")
        return None

def save_chat(chat_data: dict):
    """chat_data must contain at least id, title, model, messages (list), updated."""
    chat_id = chat_data["id"]
    chat_data["updated"] = int(time.time())
    path = _chat_path(chat_id)
    tmp = path + ".tmp"
    nmsgs = len(chat_data.get("messages", []))
    title = chat_data.get("title", "")
    print(f"[chats] save_chat {chat_id} title='{title}' msgs={nmsgs}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(chat_data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return chat_data

def delete_chat(chat_id: str):
    path = _chat_path(chat_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False

def create_new_chat(model: str = "") -> dict:
    chat_id = str(uuid.uuid4())
    now = int(time.time())
    chat = {
        "id": chat_id,
        "title": "New chat",
        "model": model,
        "messages": [],
        "created": now,
        "updated": now,
    }
    print(f"[chats] create_new_chat id={chat_id} model='{model}'")
    return save_chat(chat)

# -----------------------------------------------------------------------------
# Helpers - Model recommendations + auto download
# -----------------------------------------------------------------------------

def get_recommended_models():
    return CURATED_MODELS

def get_default_model_for_auto():
    # Prefer the first curated; can be overridden by options later
    return CURATED_MODELS[0] if CURATED_MODELS else "qwen2.5:1.5b"

def should_auto_download() -> bool:
    try:
        if os.path.exists(OPTIONS_PATH):
            with open(OPTIONS_PATH, "r", encoding="utf-8") as f:
                opts = json.load(f)
            val = opts.get("auto_download_model", False)
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes", "on")
            return bool(val)
    except Exception:
        pass
    # Fallback to env (set by run.sh)
    env = os.environ.get("AUTO_DOWNLOAD_MODEL", "false").lower()
    return env in ("true", "1", "yes", "on")

def trigger_auto_download_if_needed():
    """Fire-and-forget a pull of the default model if none are installed."""
    if not should_auto_download():
        return
    try:
        r = requests.get(f"{BACKEND}/api/tags", timeout=5)
        tags = r.json().get("models", []) if r.ok else []
        if tags:
            return  # already have something
    except Exception:
        pass

    default = get_default_model_for_auto()
    print(f"[auto-download] No models present — pulling default '{default}' in background...")
    def _pull():
        try:
            # Use the same payload the UI will use
            resp = requests.post(
                f"{BACKEND}/api/pull",
                json={"model": default, "stream": True},
                stream=True,
                timeout=600,
            )
            for line in resp.iter_lines():
                if line:
                    print("[auto-download]", line.decode("utf-8", errors="ignore"))
        except Exception as e:
            print("[auto-download] failed:", e)
    threading.Thread(target=_pull, daemon=True).start()

# -----------------------------------------------------------------------------
# Lightweight transparent proxy (preserves streaming for chat & pull)
# -----------------------------------------------------------------------------

def _proxy(to_path: str):
    """Forward the current request to the hailo-ollama backend and stream the response."""
    url = f"{BACKEND}/{to_path}"
    # Drop hop-by-hop headers
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "connection")
    }

    try:
        backend_resp = requests.request(
            method=request.method,
            url=url,
            headers=headers,
            params=request.args,
            data=request.get_data(),
            stream=True,
            timeout=300,
        )
    except requests.RequestException as e:
        return jsonify({"error": "backend_unreachable", "detail": str(e)}), 502

    # NEW: Surface binary errors clearly (especially model load failures)
    if backend_resp.status_code >= 400:
        try:
            error_body = backend_resp.json()
        except Exception:
            error_body = {"raw": backend_resp.text[:500]}
        return jsonify({
            "error": "hailo_backend_error",
            "status_code": backend_resp.status_code,
            "detail": error_body
        }), backend_resp.status_code

    def generate():
        try:
            for chunk in backend_resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        finally:
            backend_resp.close()

    # Copy important response headers
    excluded = {"content-length", "transfer-encoding", "connection"}
    resp_headers = {
        k: v for k, v in backend_resp.headers.items()
        if k.lower() not in excluded
    }

    return Response(
        generate(),
        status=backend_resp.status_code,
        headers=resp_headers,
        content_type=backend_resp.headers.get("Content-Type", "application/json"),
    )

# -----------------------------------------------------------------------------
# Routes - UI (modern OpenWebUI-like experience)
# -----------------------------------------------------------------------------

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Hailo LLM • Chat</title>
  <!-- External CDNs removed for offline/HA compatibility (Tailwind/FA).
       Basic styles provided inline below. -->
  <style>
    :root { --accent: #6366f1; }
    body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #09090b; color: #e4e4e7; margin:0; }
    .font-display { font-family: system-ui, sans-serif; font-weight: 600; }
    .flex { display: flex; }
    .h-screen { height: 100vh; }
    .overflow-hidden { overflow: hidden; }
    .w-72 { width: 18rem; }
    .border-r { border-right: 1px solid #27272a; }
    .border-zinc-800 { border-color: #27272a; }
    .bg-zinc-900 { background: #18181b; }
    .bg-zinc-800 { background: #27272a; }
    .bg-zinc-950 { background: #09090b; }
    .text-zinc-200 { color: #e4e4e7; }
    .text-zinc-500 { color: #71717a; }
    .text-zinc-400 { color: #a1a1aa; }
    .text-emerald-400 { color: #4ade80; }
    .text-amber-400 { color: #fbbf24; }
    .text-rose-400 { color: #f87171; }
    .text-indigo-300 { color: #a5b4fc; }
    .p-4 { padding: 1rem; }
    .p-3 { padding: 0.75rem; }
    .p-5 { padding: 1.25rem; }
    .px-4 { padding-left: 1rem; padding-right: 1rem; }
    .py-2 { padding-top: 0.5rem; padding-bottom: 0.5rem; }
    .py-1 { padding-top: 0.25rem; padding-bottom: 0.25rem; }
    .px-3 { padding-left: 0.75rem; padding-right: 0.75rem; }
    .py-1\.5 { padding-top: 0.375rem; padding-bottom: 0.375rem; }
    .px-5 { padding-left: 1.25rem; padding-right: 1.25rem; }
    .mt-2 { margin-top: 0.5rem; }
    .mt-3 { margin-top: 0.75rem; }
    .mt-4 { margin-top: 1rem; }
    .mt-6 { margin-top: 1.5rem; }
    .mb-4 { margin-bottom: 1rem; }
    .mb-2 { margin-bottom: 0.5rem; }
    .gap-2 { gap: 0.5rem; }
    .flex-wrap { flex-wrap: wrap; }
    #curated-models {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      max-width: 100%;
      overflow: hidden;
    }
    .model-chip {
      max-width: 100%;
      flex-shrink: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .gap-3 { gap: 0.75rem; }
    .gap-1\.5 { gap: 0.375rem; }
    .flex-col { flex-direction: column; }
    .flex-1 { flex: 1 1 0%; }
    .items-center { align-items: center; }
    .justify-between { justify-content: space-between; }
    .justify-end { justify-content: flex-end; }
    .rounded-2xl { border-radius: 1rem; }
    .rounded-3xl { border-radius: 1.5rem; }
    .rounded-xl { border-radius: 0.75rem; }
    .border { border: 1px solid #27272a; }
    .border-t { border-top: 1px solid #27272a; }
    .border-zinc-700 { border-color: #3f3f46; }
    .text-sm { font-size: 0.875rem; }
    .text-xs { font-size: 0.75rem; }
    .text-lg { font-size: 1.125rem; }
    .text-xl { font-size: 1.25rem; }
    .uppercase { text-transform: uppercase; }
    .tracking-widest { letter-spacing: 0.1em; }
    .font-semibold { font-weight: 600; }
    .font-medium { font-weight: 500; }
    .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .min-w-0 { min-width: 0; }
    .cursor-pointer { cursor: pointer; }
    .hidden { display: none; }
    .block { display: block; }
    .inline-block { display: inline-block; }
    .fixed { position: fixed; }
    .inset-0 { top:0; right:0; bottom:0; left:0; }
    .z-50 { z-index: 50; }
    .bg-black\/70 { background: rgba(0,0,0,0.7); }
    .items-center { align-items: center; }
    .justify-center { justify-content: center; }
    .max-w-lg { max-width: 32rem; }
    .max-w-sm { max-width: 24rem; }
    .m-4 { margin: 1rem; }
    .space-y-1 > * + * { margin-top: 0.25rem; }
    .space-y-3 > * + * { margin-top: 0.75rem; }
    .space-y-4 > * + * { margin-top: 1rem; }
    .transition { transition: all 0.1s ease; }
    .hover\:bg-zinc-700:hover { background: #3f3f46; }
    .hover\:bg-zinc-800:hover { background: #27272a; }
    .hover\:bg-indigo-500:hover { background: #6366f1; }
    .active\:bg-zinc-900:active { background: #18181b; }
    /* Indigo and rose backgrounds for primary action buttons (was missing - caused white/blank button bg) */
    .bg-indigo-600 { background: #6366f1; }
    .bg-indigo-500 { background: #6366f1; }
    .bg-indigo-700 { background: #4338ca; }
    .active\:bg-indigo-700:active { background: #4338ca; }
    .bg-rose-600 { background: #e11d48; }
    .bg-rose-500 { background: #f43f5e; }
    .hover\:bg-rose-500:hover { background: #f43f5e; }
    .text-indigo-400 { color: #818cf8; }
    .accent-indigo-500 { accent-color: #6366f1; }
    .w-full { width: 100%; }
    .w-4 { width: 1rem; }
    .h-4 { height: 1rem; }
    .h-12 { height: 3rem; }
    .h-9 { height: 2.25rem; }
    .w-9 { width: 2.25rem; }
    .resize-y { resize: vertical; }
    .min-h-\[52px\] { min-height: 52px; }
    .max-h-40 { max-height: 10rem; }
    .overflow-auto { overflow: auto; }
    .whitespace-pre-wrap { white-space: pre-wrap; }
    .max-w-3xl { max-width: 48rem; }
    .mx-auto { margin-left: auto; margin-right: auto; }
    .p-2 { padding: 0.5rem; }
    .p-1 { padding: 0.25rem; }
    .px-2 { padding-left: 0.5rem; padding-right: 0.5rem; }
    .py-2\.5 { padding-top: 0.625rem; padding-bottom: 0.625rem; }
    .pt-4 { padding-top: 1rem; }
    .px-1 { padding-left: 0.25rem; padding-right: 0.25rem; }
    .mt-1 { margin-top: 0.25rem; }
    .mt-1\.5 { margin-top: 0.375rem; }
    .mb-1 { margin-bottom: 0.25rem; }
    .mb-5 { margin-bottom: 1.25rem; }
    .mb-6 { margin-bottom: 1.5rem; }
    .ml-2 { margin-left: 0.5rem; }
    .text-center { text-align: center; }
    .leading-tight { line-height: 1.25; }
    .tracking-tighter { letter-spacing: -0.05em; }
    .chat-container { scrollbar-width: thin; scrollbar-color: #3f3f46 #18181b; }
    .message-bubble { max-width: 78%; padding: 0.75rem 1rem; border-radius: 1.25rem; font-size: 0.875rem; white-space: pre-wrap; color: #e4e4e7; }
    .assistant-bubble { background: #1f2937; border: 1px solid #374151; color: #e4e4e7; }
    .user-bubble { background: #6366f1; color: white; }
    .streaming::after { content: '▍'; animation: blink 1s step-end infinite; }
    @keyframes blink { 50% { opacity: 0; } }
    .sidebar { transition: transform .2s ease; }
    .modern-card { background: #111827; border: 1px solid #1f2937; border-radius: 1.5rem; }
    .model-chip { transition: all .1s ease; padding: 0.25rem 0.75rem; border-radius: 1rem; background: #27272a; border: 1px solid #3f3f46; font-size: 0.75rem; }
    .model-chip:hover { transform: translateY(-1px); box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1); }
    .hailo-glow { box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1); }
    .log-line { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 0.75rem; }
    #model-select {
      -webkit-appearance: none;
      -moz-appearance: none;
      appearance: none;
      background-image: none !important;
      background: #27272a;
      border: 1px solid #3f3f46;
      color: #e4e4e7;
      font-size: 0.875rem;
      padding: 0.375rem 2rem 0.375rem 0.75rem;
      border-radius: 1rem;
    }
    .fa-solid { font-style: normal; display: inline-block; color: inherit; font-size: 1rem; line-height: 1; vertical-align: middle; }
    i { color: inherit; }
    .fa-microchip:before { content: "⚙"; }
    .fa-plus:before { content: "+"; }
    .fa-download:before { content: "⬇"; }
    .fa-bolt:before { content: "⚡"; }
    .fa-cog:before { content: "⚙"; }
    .fa-paper-plane:before { content: "➤"; }
    .fa-stop:before { content: "■"; }
    .fa-redo:before { content: "↻"; }
    .fa-copy:before { content: "⎘"; }
    .fa-times:before { content: "×"; }
    .fa-chevron-down:before { content: "▼"; }
    .fa-robot:before { content: "🤖"; }
    .fa-trash:before { content: "🗑"; }
    .fa-check:before { content: "✓"; }
    i.fa-paper-plane { font-size: 1.25rem; }
    /* Ensure light readable icons on dark surfaces */
    button .fa-solid, .sidebar button .fa-solid { color: inherit; }
    #sidebar.collapsed {
      width: 3rem !important;
      overflow: hidden;
    }
    #sidebar.collapsed .sidebar-text,
    #sidebar.collapsed #chat-list {
      display: none !important;
    }
    #sidebar.collapsed button[title="Toggle sidebar"] {
      width: 100%;
      text-align: center;
    }
    #sidebar button {
      color: #e4e4e7;
    }
    #main-content {
      display: flex;
      flex-direction: column;
      flex: 1 1 0%;
      min-width: 0;
      height: 100%;
    }
    #chat-messages {
      flex: 1 1 auto;
      overflow-y: auto;
      padding: 1rem;
      background: #09090b;
      color: #e4e4e7;
    }
    #chat-messages .text-center {
      color: #71717a;
    }
    #message-input, input, textarea, button, select {
      color: #e4e4e7;
    }
    #message-input {
      background-color: #27272a;
      border-color: #3f3f46;
    }
    /* Primary action buttons: ensure bg + readable white text/icon on indigo/rose */
    .bg-indigo-600, button.bg-indigo-600, button[class*="indigo-600"] {
      background: #6366f1 !important;
      color: #ffffff !important;
    }
    .bg-rose-600, button.bg-rose-600 {
      background: #e11d48 !important;
      color: #ffffff !important;
    }
    button .fa-solid {
      color: inherit !important;
    }
    /* Fix remaining secondary icon buttons (top Models, minimise ☰, delete chat) appearing white or invisible.
       Use theme colors with !important for visibility on dark bg. Match background/contrast better. */
    button.text-zinc-200,
    button.text-zinc-400,
    #sidebar button,
    button[onclick*="openModelManager"] {
      color: #e4e4e7 !important;
    }
    button.text-zinc-200 i.fa-solid,
    button.text-zinc-400 i.fa-solid,
    #sidebar button i.fa-solid,
    button[onclick*="openModelManager"] i.fa-solid {
      color: inherit !important;
    }
    /* Keep accent for download icon but ensure it shows */
    button[onclick*="openModelManager"] i.fa-solid {
      color: #818cf8 !important;
    }
    /* Slightly softer for secondary to "match" dark theme better */
    .text-zinc-400 {
      color: #a1a1aa !important;
    }
  </style>
</head>
<body class="bg-zinc-950 text-zinc-200">
  <div class="flex h-screen overflow-hidden">
    <!-- Sidebar -->
    <div id="sidebar" class="w-72 border-r border-zinc-800 bg-zinc-900 flex flex-col">
      <!-- Header -->
      <div class="p-4 border-b border-zinc-800 flex items-center gap-3">
        <button onclick="toggleSidebar()" class="text-zinc-200 hover:text-white p-1 text-lg leading-none" title="Toggle sidebar" aria-label="Toggle sidebar" style="color:#e4e4e7">☰</button>
        <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white">
          <i class="fa-solid fa-microchip text-lg"></i>
        </div>
        <div class="sidebar-text">
          <div class="font-semibold font-display text-xl tracking-tighter">Hailo LLM</div>
          <div class="text-[10px] text-zinc-500 -mt-0.5">Hailo-10H + Model Zoo</div>
        </div>
      </div>

      <!-- New Chat -->
      <div class="p-3">
        <button onclick="createNewChat()"
                class="w-full flex items-center justify-center gap-2 rounded-2xl bg-zinc-800 hover:bg-zinc-700 active:bg-zinc-900 transition px-4 py-2.5 text-sm font-medium text-zinc-200">
          <i class="fa-solid fa-plus"></i>
          <span>New chat</span>
        </button>
      </div>

      <!-- Chat History -->
      <div class="flex-1 overflow-auto px-2 chat-container" id="chat-list">
        <!-- Populated by JS -->
      </div>

      <!-- Footer / Status -->
      <div class="p-3 border-t border-zinc-800 text-xs">
        <div class="flex items-center gap-2 text-zinc-400">
          <div id="device-status" class="flex items-center gap-1.5">
            <i class="fa-solid fa-microchip"></i>
            <span id="device-text">Checking device...</span>
          </div>
        </div>
        <div class="mt-1 text-[10px] text-zinc-500">Models persist across reboots</div>
      </div>
    </div>

    <!-- Main Area -->
    <div id="main-content" class="flex-1 flex flex-col min-w-0">
      <!-- Top bar -->
      <div class="h-14 border-b border-zinc-800 px-4 flex items-center justify-between bg-zinc-900/70 backdrop-blur">
        <div class="flex items-center gap-3">
          <!-- Model selector -->
          <div class="flex items-center gap-2">
            <div class="text-xs uppercase tracking-widest text-zinc-500">Model</div>
            <div class="relative">
              <select id="model-select" onchange="onModelChange()"
                      class="appearance-none bg-zinc-800 border border-zinc-700 text-sm rounded-2xl pl-3 pr-8 py-1.5 focus:outline-none focus:border-indigo-500">
              </select>
              <i class="fa-solid fa-chevron-down absolute right-3 top-2.5 text-xs text-zinc-400 pointer-events-none"></i>
            </div>
            <button onclick="openModelManager()"
                    class="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-2xl border border-zinc-700 hover:bg-zinc-800 active:bg-zinc-900 text-zinc-200">
              <i class="fa-solid fa-download" style="color:#818cf8"></i>
              <span style="color:#e4e4e7">Models</span>
            </button>
          </div>
        </div>

        <div class="flex items-center gap-2 text-xs">
          <div class="px-3 py-1 rounded-2xl bg-zinc-800 text-zinc-400 flex items-center gap-1.5">
            <i class="fa-solid fa-bolt text-emerald-400"></i>
            <span>Hailo accelerated</span>
          </div>
          <!-- Settings integrated into Models panel -->
        </div>
      </div>

      <!-- Chat Area -->
      <div class="flex-1 overflow-auto p-6 chat-container bg-zinc-950" id="chat-messages">
        <div id="empty-state" class="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
          <div class="w-16 h-16 rounded-3xl bg-zinc-900 flex items-center justify-center mb-6">
            <i class="fa-solid fa-robot text-4xl text-indigo-400"></i>
          </div>
          <div class="text-2xl font-semibold tracking-tighter">Ready when you are</div>
          <p class="text-zinc-400 mt-2">Select a model above and start a conversation.<br>Everything is stored persistently on HAOS.</p>
          <div class="mt-6 text-xs text-zinc-500">Powered by Hailo-10H NPU • Ollama-compatible API</div>
        </div>
        <!-- Messages injected here by JS -->
      </div>

      <!-- Composer -->
      <div class="border-t border-zinc-800 p-4 bg-zinc-900">
        <div class="max-w-3xl mx-auto">
          <div class="flex gap-2 items-end">
            <div class="flex-1 relative">
              <textarea id="message-input" rows="1"
                        class="w-full resize-y min-h-[52px] max-h-40 bg-zinc-800 border border-zinc-700 focus:border-indigo-500 rounded-3xl px-5 py-3 text-sm outline-none"
                        placeholder="Message the model... (Shift+Enter for newline)"
                        onkeydown="if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }"></textarea>
            </div>
            <button onclick="sendMessage()"
                    class="h-12 w-12 flex-shrink-0 rounded-3xl bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 transition flex items-center justify-center text-white">
              <i class="fa-solid fa-paper-plane"></i>
            </button>
            <button onclick="stopGeneration()" id="stop-btn"
                    class="hidden h-12 w-12 flex-shrink-0 rounded-3xl bg-rose-600 hover:bg-rose-500 items-center justify-center text-white">
              <i class="fa-solid fa-stop"></i>
            </button>
          </div>
          <div class="text-[10px] text-zinc-500 mt-1.5 px-1 flex items-center gap-2">
            <span>Model:</span> <span id="composer-model" class="font-mono text-zinc-400"></span>
            <span class="mx-1">•</span>
            <span class="cursor-pointer hover:text-zinc-300" onclick="openModelManager()">change</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Model Manager Modal -->
  <div id="model-modal" onclick="if (event.target.id === 'model-modal') closeModelManager()" class="fixed inset-0 bg-black/70 flex items-center justify-center z-50" style="display: none;">
    <div onclick="event.stopImmediatePropagation()" class="modern-card w-full max-w-lg rounded-3xl p-5 m-4">
      <div class="flex justify-between items-center mb-4">
        <div class="font-semibold text-lg">Models</div>
        <button onclick="closeModelManager()" class="text-zinc-400 hover:text-white"><i class="fa-solid fa-times text-xl"></i></button>
      </div>

      <!-- Installed -->
      <div class="mb-4">
        <div class="uppercase text-xs tracking-wider text-zinc-500 mb-2 px-1">Installed</div>
        <div id="installed-models" class="space-y-1 text-sm"></div>
        <div id="loaded-note" class="text-[10px] text-emerald-400 px-1 mt-1"></div>
      </div>

      <!-- Download curated -->
      <div class="mb-4">
        <div class="uppercase text-xs tracking-wider text-zinc-500 mb-2 px-1">Recommended for Hailo-10H</div>
        <div id="curated-models" class="flex flex-wrap gap-2"></div>
      </div>

      <!-- Free text pull -->
      <div>
        <div class="uppercase text-xs tracking-wider text-zinc-500 mb-2 px-1">Pull custom model</div>
        <div class="flex gap-2">
          <input id="custom-model-input" type="text" placeholder="qwen2.5:1.5b or other tag"
                 class="flex-1 bg-zinc-900 border border-zinc-700 rounded-2xl px-4 py-2 text-sm focus:border-indigo-500 outline-none"/>
          <button onclick="pullCustomModel()" 
                  class="px-5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-sm font-medium text-white">Pull</button>
        </div>
        <div id="pull-progress" class="mt-3 hidden text-xs log-line bg-zinc-900 border border-zinc-800 rounded-2xl p-2 max-h-24 overflow-auto"></div>
      </div>

      <!-- Settings section (integrated into Models panel for better panel layout) -->
      <div class="mt-4 pt-4 border-t border-zinc-700">
        <div class="uppercase text-xs tracking-wider text-zinc-500 mb-2 px-1">Settings</div>
        <div class="space-y-3 text-sm">
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Keep Alive</label>
            <input id="setting-keep-alive" type="text" class="w-full bg-zinc-900 border border-zinc-700 rounded-2xl px-3 py-1.5 text-sm" value="300m"/>
            <div class="text-[10px] text-zinc-500 mt-0.5">e.g. 300m, 1h, -1 (forever)</div>
          </div>
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm">Auto-download default model</div>
              <div class="text-xs text-zinc-500">On first start if no models present</div>
            </div>
            <input type="checkbox" id="setting-auto-download" class="accent-indigo-500 w-4 h-4"/>
          </div>
        </div>
        <div class="mt-3 flex justify-end">
          <button onclick="saveSettings(); closeModelManager();" class="px-3 py-1 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-xs text-white">Save Settings</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    // ============== Tiny client-side app ==============
    // Use ingress base so API calls go to the correct proxied path under HA ingress.
    // This makes /api/* etc. resolve to /api/hassio_ingress/<token>/api/* which the
    // supervisor forwards to the addon on port 8000.
    const INGRESS_BASE = (window.location.pathname || '/').replace(/\/$/, '') + '/';

    let currentChatId = null;
    let currentModel = "";
    let abortController = null;

    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    function toggleSidebar() {
      const sb = $('#sidebar');
      if (sb) sb.classList.toggle('collapsed');
    }

    function fmtTime(ts) {
      if (!ts) return '';
      const d = new Date(ts * 1000);
      return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
    }

    async function loadModelsIntoSelect() {
      try {
        const res = await fetch(INGRESS_BASE + 'api/tags');
        const data = await res.json();
        const sel = $('#model-select');
        sel.innerHTML = '';
        const models = (data.models || []).map(m => m.name || m.model).filter(Boolean);
        
        if (models.length === 0) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = '— pull a model first —';
          sel.appendChild(opt);
          sel.disabled = true;
          return;
        }
        models.forEach(name => {
          const opt = document.createElement('option');
          opt.value = name;
          opt.textContent = name;
          sel.appendChild(opt);
        });
        if (currentModel && models.includes(currentModel)) {
          sel.value = currentModel;
        } else if (!currentModel) {
          currentModel = models[0];
          sel.value = currentModel;
        }
        $('#composer-model').textContent = sel.value || '—';
      } catch (e) {
        console.warn('Failed to load models', e);
      }
    }

    function onModelChange() {
      const sel = $('#model-select');
      currentModel = sel.value;
      $('#composer-model').textContent = currentModel || '—';
      if (currentChatId) {
        // Update model on current chat
        fetchChat(currentChatId).then(chat => {
          if (chat) {
            chat.model = currentModel;
            saveChatRemote(chat);
          }
        });
      }
    }

    async function fetchChat(chatId) {
      try {
        const res = await fetch(INGRESS_BASE + 'api/chats/' + chatId);
        if (!res.ok) {
          console.warn('[fetchChat] not ok', chatId, res.status);
          return null;
        }
        return res.json();
      } catch (e) {
        console.warn('[fetchChat] error', chatId, e);
        return null;
      }
    }

    async function saveChatRemote(chat) {
      try {
        const res = await fetch(INGRESS_BASE + 'api/chats/' + chat.id, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(chat)
        });
        if (!res.ok) {
          const t = await res.text().catch(() => '');
          console.error('[saveChatRemote] bad status', res.status, t, 'for', chat.id);
        }
      } catch (e) {
        console.error('[saveChatRemote] network error', e);
      }
      // Always attempt list refresh but never throw to callers
      try {
        await refreshChatList();
      } catch (e) {
        console.warn('[saveChatRemote] refresh failed (non-fatal)', e);
      }
    }

    async function refreshChatList() {
      try {
        const res = await fetch(INGRESS_BASE + 'api/chats');
        if (!res.ok) throw new Error('list status ' + res.status);
        const list = await res.json();
        const container = $('#chat-list');
        container.innerHTML = '';
        list.forEach(c => {
          const div = document.createElement('div');
          const mc = c.message_count || 0;
          div.className = `px-3 py-2 rounded-2xl mx-1 mb-1 text-sm cursor-pointer flex justify-between items-center gap-2 hover:bg-zinc-800 ${currentChatId === c.id ? 'bg-zinc-800' : ''}`;
          div.innerHTML = `
            <div class="flex-1 min-w-0" onclick="switchToChat('${c.id}')">
              <div class="truncate font-medium">${c.title || 'Untitled'} <span class="text-[10px] text-zinc-500">(${mc})</span></div>
              <div class="text-xs text-zinc-500 truncate">${c.model || ''}</div>
            </div>
            <button onclick="event.stopImmediatePropagation(); deleteChat('${c.id}');" class="text-zinc-400 hover:text-rose-400 p-1" title="Delete chat"><i class="fa-solid fa-trash text-xs" style="color:#a1a1aa"></i></button>
          `;
          container.appendChild(div);
        });
      } catch (e) {
        console.error('[refreshChatList] failed', e);
      }
    }

    function renderMessages(chat) {
      const area = $('#chat-messages');
      area.innerHTML = '';
      $('#empty-state').classList.add('hidden');

      console.log('[renderMessages] msgs=', chat && chat.messages ? chat.messages.length : 0, 'inflight=', generationInFlight);

      if (!chat || !chat.messages || chat.messages.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-center text-zinc-500 py-12';
        empty.textContent = 'Start the conversation';
        area.appendChild(empty);
        return;
      }

      chat.messages.forEach((msg, idx) => {
        const bubble = document.createElement('div');
        bubble.className = `flex mb-5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`;

        const inner = document.createElement('div');
        inner.className = `message-bubble rounded-3xl px-4 py-3 text-sm whitespace-pre-wrap ${msg.role === 'user' ? 'user-bubble' : 'assistant-bubble border border-zinc-700'}`;

        // Simple markdown-ish rendering for assistant (code blocks + basic)
        let content = msg.content || '';
        if (msg.role === 'assistant') {
          content = content.replace(/```([\s\S]*?)```/g, '<pre class="bg-zinc-950 p-2 rounded-xl my-1 overflow-auto text-xs">$1</pre>');
          content = content.replace(/\n/g, '<br>');
        }

        const isLastAssistant = (msg.role === 'assistant' && idx === chat.messages.length - 1);
        if (isLastAssistant && !content && generationInFlight) {
          inner.innerHTML = '<span class="opacity-50">Thinking...</span>';
        } else {
          inner.innerHTML = content || '<span class="opacity-50">(empty)</span>';
        }

        // Live cursor while generating the last assistant message
        if (isLastAssistant && generationInFlight) {
          inner.classList.add('streaming');
        }

        const meta = document.createElement('div');
        meta.className = `text-[10px] mt-1 px-1 flex gap-2 items-center ${msg.role === 'user' ? 'justify-end text-indigo-200' : 'text-zinc-400'}`;
        meta.innerHTML = `<span>${fmtTime(msg.ts)}</span>`;

        if (msg.role === 'assistant') {
          const actions = document.createElement('span');
          actions.className = 'ml-2 flex gap-1 text-xs';
          actions.innerHTML = `
            <button class="hover:text-white px-1" onclick="regenerate(${idx})"><i class="fa-solid fa-redo"></i></button>
            <button class="hover:text-white px-1" onclick="copyMessage(this)"><i class="fa-solid fa-copy"></i></button>
          `;
          meta.appendChild(actions);
        }

        const wrapper = document.createElement('div');
        wrapper.appendChild(inner);
        wrapper.appendChild(meta);
        bubble.appendChild(wrapper);
        area.appendChild(bubble);
      });
      area.scrollTop = area.scrollHeight;
    }

    async function switchToChat(chatId) {
      console.log('[switchToChat]', chatId);
      currentChatId = chatId;
      const chat = await fetchChat(chatId);
      if (!chat) {
        console.warn('[switchToChat] fetch failed for', chatId);
        return;
      }
      if (chat.model) {
        currentModel = chat.model;
        const sel = $('#model-select');
        if ([...sel.options].some(o => o.value === currentModel)) sel.value = currentModel;
        $('#composer-model').textContent = currentModel;
      }
      renderMessages(chat);
      await refreshChatList();
    }

    async function createNewChat(preferredModel) {
      const sel = $('#model-select');
      const model = preferredModel || sel.value || currentModel || '';
      console.log('[createNewChat] requesting with model', model);
      const resp = await fetch(INGRESS_BASE + 'api/chats', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ model })
      });
      const chat = await resp.json();
      console.log('[createNewChat] got', chat);
      currentChatId = chat.id;
      currentModel = chat.model || model;
      sel.value = currentModel;
      $('#composer-model').textContent = currentModel;
      renderMessages(chat);
      await refreshChatList();
      $('#message-input').focus();
    }

    async function deleteChat(chatId) {
      if (!confirm('Delete this conversation?')) return;
      await fetch(INGRESS_BASE + 'api/chats/' + chatId, { method: 'DELETE' });
      if (currentChatId === chatId) {
        currentChatId = null;
        $('#chat-messages').innerHTML = '';
        $('#empty-state').classList.remove('hidden');
      }
      await refreshChatList();
    }

    let generationInFlight = false;

    async function sendMessage() {
      const input = $('#message-input');
      const text = input.value.trim();
      if (!text || generationInFlight) return;

      // Clear input immediately so the typed text never "stays" on submit.
      // Do this before any awaits that might early-return (e.g. fetchChat failing).
      input.value = '';

      if (!currentChatId) {
        await createNewChat();
      }

      // Try to fetch fresh chat, but fall back to a minimal object so we always
      // show the user message even if persistence lookup temporarily fails.
      let chat = await fetchChat(currentChatId);
      if (!chat) {
        console.warn('[send] fetchChat failed after submit - using local chat object');
        chat = { id: currentChatId, messages: [], model: currentModel || '' };
      }

      console.log('[send] chat before user push, msgs=', chat.messages.length, 'id=', currentChatId);

      // append user message - OPTIMISTIC: render immediately, persist async
      const userMsg = { role: 'user', content: text, ts: Math.floor(Date.now()/1000) };
      chat.messages.push(userMsg);
      if (!chat.model) {
        chat.model = currentModel;
      }

      // Derive a useful title from the first real user message
      if (!chat.title || chat.title === 'New chat' || chat.title === 'Untitled') {
        const t = text.trim();
        chat.title = t.length > 48 ? t.slice(0, 48) + '...' : t;
      }

      renderMessages(chat);                 // user sees their message RIGHT NOW
      saveChatRemote(chat);                 // fire-and-forget for sidebar/history

      // call backend (proxied)
      generationInFlight = true;
      const stopBtn = $('#stop-btn');
      stopBtn.classList.remove('hidden');
      stopBtn.classList.add('flex');

      abortController = new AbortController();

      // helper: tolerant content extraction (handles hailo/ollama variants + common alternatives)
      function extractToken(obj) {
        if (!obj) return '';
        if (obj.message && typeof obj.message.content === 'string') return obj.message.content;
        if (typeof obj.content === 'string') return obj.content;
        if (typeof obj.response === 'string') return obj.response;
        if (obj.delta && typeof obj.delta.content === 'string') return obj.delta.content;
        if (obj.message && typeof obj.message === 'string') return obj.message; // rare
        if (obj.text && typeof obj.text === 'string') return obj.text;
        if (obj.error) return '[error] ' + (obj.error.message || obj.error || '');
        return '';
      }

      // ALWAYS create assistant stub immediately
      let assistantMessage = { role: 'assistant', content: '', ts: Math.floor(Date.now()/1000) };
      chat.messages.push(assistantMessage);
      renderMessages(chat);                 // show "Thinking..." immediately
      saveChatRemote(chat);

      console.log('[send] starting /api/chat for model', currentModel || chat.model, 'with', chat.messages.length - 1, 'messages to backend');

      // Make sure the LLM is loaded before the real chat (handles "LLM not loaded" from backend)
      await primeModel(currentModel || chat.model);

      try {
        const res = await fetch(INGRESS_BASE + 'api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: currentModel || chat.model,
            messages: chat.messages.slice(0, -1).map(m => ({ role: m.role, content: m.content })), // exclude the empty stub
            stream: true   // keep minimal payload - oatpp backend is strict about extra fields
          }),
          signal: abortController.signal
        });

        console.log('[send] /api/chat response', res.status, res.headers.get('content-type'));

        if (!res.ok) {
          const txt = await res.text().catch(() => '');
          throw new Error('Chat request failed: ' + res.status + ' ' + txt);
        }

        // Robust reader: handle both full JSON (stream:false style) and NDJSON stream lines
        const ct = (res.headers.get('content-type') || '').toLowerCase();
        let gotContent = false;

        if (ct.includes('json') && !ct.includes('stream')) {
          // Full single object response
          try {
            const data = await res.json();
            console.log('[send] full json response data', data);
            const tok = extractToken(data) || (data.message && data.message.content) || data.response || '';
            if (tok) {
              assistantMessage.content = tok;
              gotContent = true;
            }
          } catch (je) {
            console.warn('[send] json() failed, falling back to stream reader', je);
          }
        }

        if (!gotContent) {
          // NDJSON / streaming reader (pattern that works for /api/pull)
          const reader = res.body ? res.body.getReader() : null;
          if (reader) {
            const dec = new TextDecoder();
            let buf = '';
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              buf += dec.decode(value, { stream: true });
              const lines = buf.split('\n');
              buf = lines.pop() || '';
              for (const line of lines) {
                if (!line.trim()) continue;
                try {
                  const obj = JSON.parse(line);
                  // Log EVERY chunk for debugging what the native backend actually returns
                  console.log('[send raw chunk]', obj);

                  const tok = extractToken(obj);
                  if (tok) {
                    assistantMessage.content += tok;
                    gotContent = true;
                    renderMessages(chat);   // live update as tokens arrive
                  } else if (obj) {
                    // Helpful: if we get objects but no text token, surface it
                    console.warn('[send] chunk had no extractable token. keys=', Object.keys(obj));
                  }
                  if (obj.done === true) {
                    console.log('[send] done=true received');
                    break;
                  }
                } catch (pe) {}
              }
            }
          }
        }

        // If we got nothing at all, give a clear diagnostic
        if (!assistantMessage.content) {
          assistantMessage.content = '[no content returned by model]';
        }

        // final render + persist
        renderMessages(chat);
        saveChatRemote(chat);
        console.log('[send] final assistant content length=', assistantMessage.content.length);
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('[send] generation error', err);
          if (!assistantMessage.content) {
            let msg = '[generation failed] ' + (err.message || 'see browser console and addon logs');
            if (err.message && err.message.includes('hailo_backend_error')) {
              msg += ' (check /api/logs for VDevice or model load errors)';
            }
            assistantMessage.content = msg;
          }
          renderMessages(chat);
        }
        if (currentChatId) {
          saveChatRemote(chat).catch(() => {});
        }
      } finally {
        generationInFlight = false;
        stopBtn.classList.add('hidden');
        stopBtn.classList.remove('flex');
        abortController = null;
        refreshChatList().catch(() => {});
      }
    }

    function stopGeneration() {
      if (abortController) {
        abortController.abort();
      }
    }

    function copyMessage(btn) {
      const bubble = btn.closest('.message-bubble');
      if (!bubble) return;
      navigator.clipboard.writeText(bubble.innerText).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-check"></i>';
        setTimeout(() => { btn.innerHTML = orig; }, 1200);
      });
    }

    async function regenerate(idx) {
      if (!currentChatId) return;
      const chat = await fetchChat(currentChatId);
      if (!chat || !chat.messages.length) return;
      // remove everything after the chosen user message
      chat.messages = chat.messages.slice(0, idx + 1);
      await saveChatRemote(chat);
      renderMessages(chat);
      // re-send the last user message
      $('#message-input').value = chat.messages[chat.messages.length-1].content;
      await sendMessage();
    }

    // ---------------- Model manager ----------------
    let pullInProgress = false;

    function openModelManager() {
      const modal = $('#model-modal');
      modal.style.display = 'flex';
      refreshInstalledModels();
      refreshLoadedModels();
      renderCuratedModels();
      $('#pull-progress').classList.add('hidden');
    }

    function closeModelManager() {
      const modal = $('#model-modal');
      modal.style.display = 'none';
      // refresh model list in header
      loadModelsIntoSelect();
    }

    async function refreshInstalledModels() {
      const container = $('#installed-models');
      container.innerHTML = '<div class="text-xs text-zinc-500 px-1 py-1">Loading...</div>';
      try {
        const res = await fetch(INGRESS_BASE + 'api/tags');
        const data = await res.json();
        const models = data.models || [];
        container.innerHTML = '';
        if (models.length === 0) {
          container.innerHTML = '<div class="text-xs px-2 py-1 text-zinc-500">No models installed yet.</div>';
          return;
        }
        models.forEach(m => {
          const name = m.name || m.model;
          const div = document.createElement('div');
          div.className = 'flex items-center justify-between px-3 py-1.5 bg-zinc-800 rounded-2xl text-sm';
          div.innerHTML = `
            <div class="font-mono text-indigo-300">${name}</div>
            <button class="text-rose-400 hover:text-rose-300 text-xs px-2" onclick="deleteModel('${name}', this)" title="Delete model">delete</button>
          `;
          container.appendChild(div);
        });
      } catch (e) {
        container.innerHTML = '<div class="text-xs text-amber-400 px-1">Backend starting or no models yet. Use the recommended buttons or pull one.</div>';
      }
    }

    async function refreshLoadedModels() {
      // /api/ps shows models currently loaded into the LLM runtime (fixes "LLM not loaded" visibility)
      try {
        const res = await fetch(INGRESS_BASE + 'api/ps');
        if (!res.ok) return;
        const data = await res.json();
        const loaded = (data.models || data || []).map(m => m.name || m.model).filter(Boolean);
        const note = document.getElementById('loaded-note');
        if (note) {
          note.textContent = loaded.length ? 'Loaded: ' + loaded.join(', ') : 'No LLM currently loaded (will prime on first chat)';
        }
      } catch (e) {}
    }

    function renderCuratedModels() {
      const container = $('#curated-models');
      container.innerHTML = '';
      let models = window.CURATED || [];
      // Try to query available models from the binary if supported
      // (e.g. /hailo/v1/list may return list of pullable models for the zoo)
      fetch(INGRESS_BASE + 'hailo/v1/list')
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data) {
            if (Array.isArray(data)) models = data;
            else if (data.models && Array.isArray(data.models)) models = data.models;
          }
          populateCurated(container, models);
        })
        .catch(() => {
          populateCurated(container, models);
        });
    }

    function populateCurated(container, models) {
      container.innerHTML = '';
      models.forEach(name => {
        const btn = document.createElement('button');
        btn.className = 'model-chip text-xs px-3 py-1 rounded-2xl bg-zinc-800 hover:bg-zinc-700 border border-zinc-700';
        btn.textContent = name;
        btn.onclick = () => pullModel(name, btn);
        container.appendChild(btn);
      });
    }

    async function pullModel(name, btnEl) {
      if (pullInProgress) return;
      pullInProgress = true;
      const progress = $('#pull-progress');
      progress.classList.remove('hidden');
      progress.innerHTML = `
        <div id="pull-status" class="text-emerald-400">Pulling ${name}...</div>
        <div id="pull-bar-container" style="height:6px; background:#27272a; border-radius:3px; margin-top:6px; overflow:hidden;">
          <div id="pull-bar" style="height:100%; width:0%; background:#4ade80; transition:width 0.2s;"></div>
        </div>
      `;

      try {
        const res = await fetch(INGRESS_BASE + 'api/pull', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ model: name, stream: true })
        });
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          buf += dec.decode(value, {stream:true});
          const lines = buf.split('\n'); buf = lines.pop() || '';
          for (const l of lines) {
            if (!l.trim()) continue;
            try {
              const obj = JSON.parse(l);
              const statusEl = document.getElementById('pull-status');
              const barEl = document.getElementById('pull-bar');
              if (obj.status) {
                let txt = obj.status;
                if (obj.completed && obj.total) {
                  const pct = Math.round(100 * obj.completed / obj.total);
                  txt += ` (${pct}%)`;
                  if (barEl) barEl.style.width = pct + '%';
                }
                if (statusEl) statusEl.textContent = txt;
              }
            } catch(e){}
          }
        }
        const statusEl = document.getElementById('pull-status');
        if (statusEl) statusEl.textContent = '✓ Done';
        const barEl = document.getElementById('pull-bar');
        if (barEl) barEl.style.width = '100%';
        await refreshInstalledModels();
        await loadModelsIntoSelect();
        // Prime / load the LLM into memory (the backend sometimes requires an initial
        // generate or chat to move from "downloaded" to "LLM loaded" state).
        // This prevents the "LLM not loaded" 500 on the first real chat.
        primeModel(name);
      } catch (e) {
        progress.innerHTML += `<div class="text-rose-400">Error: ${e.message}</div>`;
      } finally {
        pullInProgress = false;
        setTimeout(() => { progress.classList.add('hidden'); progress.innerHTML = ''; }, 2200);
      }
    }

    async function pullCustomModel() {
      const input = $('#custom-model-input');
      const name = input.value.trim();
      if (!name) return;
      await pullModel(name);
      input.value = '';
    }

    async function primeModel(model) {
      if (!model) return;
      console.log('[prime] attempting to load LLM for', model, '(to avoid "LLM not loaded" error)');
      try {
        // Use a minimal generate request. This often forces the backend to initialize
        // the LLM runtime / VDevice + HEF for the model. Chat will then succeed.
        const res = await fetch(INGRESS_BASE + 'api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model, prompt: ' ', stream: false })
        });
        console.log('[prime] generate status', res.status);
        // We don't care much about the result; the side effect is loading the model.
      } catch (e) {
        console.warn('[prime] failed', e);
      }
    }

    async function deleteModel(name, btn) {
      if (!confirm(`Delete model "${name}"?`)) return;
      btn.textContent = '…';
      try {
        await fetch(INGRESS_BASE + 'api/delete', {
          method: 'DELETE',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ name })
        });
      } catch(e){}
      await refreshInstalledModels();
      await loadModelsIntoSelect();
    }

    // Settings are now inside the Models panel.
    // The save just alerts (full persistence is via HA addon config + restart).
    async function saveSettings() {
      // For now we just close (user can change via HA UI options)
      alert('Settings are read at addon start from the Home Assistant add-on configuration.\nChange them in the add-on UI and restart the addon.');
      // The panel is closed via the button in the HTML
    }

    // ---------------- Boot ----------------
    window.CURATED = ["qwen2.5:1.5b", "qwen2:1.5b", "phi3:3.8b"];

    async function initUI() {
      // Device status
      try {
        const h = await fetch(INGRESS_BASE + 'health');
        const data = await h.json();
        const el = $('#device-text');
        if (data.hailo_device) {
          el.innerHTML = `<span class="text-emerald-400">Hailo device ready</span>`;
        } else {
          el.innerHTML = `<span class="text-amber-400">No Hailo device</span>`;
        }
      } catch(e) {
        $('#device-text').innerHTML = '<span class="text-amber-400">Backend starting (check logs if stuck)</span>';
      }

      // Initial model load
      await loadModelsIntoSelect();

      // Chat list + possibly auto-create first chat
      await refreshChatList();

      // If no chats, start one
      const listRes = await fetch(INGRESS_BASE + 'api/chats');
      const chats = await listRes.json();
      console.log('[init] existing chats on load:', chats.length);
      if (chats.length === 0) {
        await createNewChat();
      } else {
        // load most recent
        await switchToChat(chats[0].id);
      }

      // Auto download hook (non-blocking)
      // The server already triggers this on startup if configured.
      // We just refresh the list after a delay in case it is happening.
      setTimeout(() => { loadModelsIntoSelect(); }, 8000);

      // Keyboard hint
      const input = $('#message-input');
      input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 160) + 'px';
      });

      // Auto-load models panel on first load (user request)
      openModelManager();

      // Collapse sidebar on small screens / mobile
      if (window.innerWidth < 768) {
        const sb = $('#sidebar');
        if (sb) sb.classList.add('collapsed');
      }
    }

    // Make curated list available to the embedded script
    document.addEventListener('DOMContentLoaded', initUI);
  </script>
</body>
</html>
"""

# Note: We intentionally do NOT define a root route here.
# The catch-all UI server is registered *after* all API routes (see below)
# so that /api/* and /hailo/* are always handled by the proxy first.

# -----------------------------------------------------------------------------
# Chat persistence API (used by the UI)
# -----------------------------------------------------------------------------

@app.route("/api/chats", methods=["GET"])
def api_list_chats():
    return jsonify(list_chats())

@app.route("/api/chats", methods=["POST"])
def api_create_chat():
    payload = request.get_json(silent=True) or {}
    model = payload.get("model", "")
    chat = create_new_chat(model)
    print(f"[chats] api_create_chat -> id={chat['id']} model={model}")
    return jsonify(chat), 201

@app.route("/api/chats/<chat_id>", methods=["GET"])
def api_get_chat(chat_id):
    chat = load_chat(chat_id)
    if not chat:
        return jsonify({"error": "not_found"}), 404
    return jsonify(chat)

@app.route("/api/chats/<chat_id>", methods=["POST"])
def api_save_chat(chat_id):
    data = request.get_json(force=True)
    if not data or data.get("id") != chat_id:
        print(f"[chats] api_save_chat {chat_id} REJECTED invalid payload")
        return jsonify({"error": "invalid_payload"}), 400
    saved = save_chat(data)
    return jsonify(saved)

@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def api_delete_chat(chat_id):
    ok = delete_chat(chat_id)
    return ("", 204) if ok else ("", 404)

# -----------------------------------------------------------------------------
# Transparent proxy routes for Ollama-compatible surface
# (so the service still "looks and feels like an ollama backend")
# -----------------------------------------------------------------------------

@app.route("/api/<path:path>", methods=["GET", "POST", "DELETE", "PUT", "PATCH"])
def proxy_api(path):
    return _proxy(f"api/{path}")

@app.route("/hailo/<path:path>", methods=["GET", "POST", "DELETE", "PUT", "PATCH"])
def proxy_hailo(path):
    return _proxy(f"hailo/{path}")

# -----------------------------------------------------------------------------
# Health & utilities (extended)
# -----------------------------------------------------------------------------

@app.route("/health")
def health():
    device = os.path.exists("/dev/hailo0")
    backend_ok = False
    try:
        r = requests.get(f"{BACKEND}/api/tags", timeout=2)
        backend_ok = r.ok
    except Exception:
        pass
    return jsonify({
        "status": "healthy" if (device and backend_ok) else "degraded",
        "hailo_device": device,
        "backend_reachable": backend_ok,
        "backend": BACKEND,
        "models_persisted_at": MODELS_DIR,  # blob dir under XDG_DATA_HOME=/media/hailo_llm (see hailo_model_zoo_genai)
        "chats_persisted_at": CHATS_DIR,
        "hailo_log": "/data/hailo-ollama.log",
    })

@app.route("/api/ui/recommended-models")
def recommended_models():
    return jsonify({"recommended": get_recommended_models()})

@app.route("/api/logs")
def api_logs():
    """Return last ~100 lines of the hailo-ollama backend log for troubleshooting."""
    log_path = "/data/hailo-ollama.log"
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-100:]
        # Strip ANSI color codes for cleaner output
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_lines = [ansi_escape.sub('', line) for line in lines]
        return jsonify({"path": log_path, "lines": len(clean_lines), "log": "".join(clean_lines)})
    except Exception as e:
        return jsonify({"path": log_path, "error": str(e)})

@app.route("/api/debug/device")
def debug_device():
    """Quick check for processes using /dev/hailo0 (container view only).
    Note: This only sees processes inside the addon container. Check on the host for full picture."""
    import os
    result = {"device": "/dev/hailo0", "holders": [], "note": "container view only - run similar check on host"}
    if not os.path.exists("/dev/hailo0"):
        result["error"] = "no device"
        return jsonify(result)
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                fd_dir = f"/proc/{pid}/fd"
                if os.path.isdir(fd_dir):
                    for fd in os.listdir(fd_dir):
                        try:
                            target = os.readlink(f"{fd_dir}/{fd}")
                            if "/dev/hailo0" in target:
                                cmd = ""
                                try:
                                    with open(f"/proc/{pid}/cmdline", "rb") as f:
                                        cmd = f.read().replace(b"\0", b" ").decode(errors="ignore").strip()
                                except:
                                    pass
                                result["holders"].append({"pid": pid, "cmd": cmd[:200]})
                        except:
                            pass
            except:
                pass
    except Exception as e:
        result["error"] = str(e)
    return jsonify(result)

# -----------------------------------------------------------------------------
# UI catch-all (must be registered AFTER all /api and /hailo routes)
#
# This ensures that the beautiful web UI is served for the root (and any
# other non-API path) that the HA ingress might use. This pattern is
# important for reliable rendering inside Home Assistant panels.
# Without it, some ingress path variations can cause the browser to
# download the response as "downloadfile.bin" instead of rendering HTML.
# -----------------------------------------------------------------------------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_ui(path):
    # Only serve the UI for paths that are not API routes.
    # (The specific and generic /api/* and /hailo/* routes above will have
    # already matched if this was an API request.)
    if path.startswith("api/") or path.startswith("hailo/"):
        return "Not Found", 404

    print(f"[hailo-llm] Serving UI for path='/{path}' (this should appear in addon logs)")
    resp = Response(INDEX_HTML, mimetype="text/html; charset=utf-8")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    # Helpful for iframe/panel embedding in HA
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp

# -----------------------------------------------------------------------------
# Startup
# -----------------------------------------------------------------------------

def run():
    # Best-effort auto-download in background (if enabled in options)
    threading.Thread(target=trigger_auto_download_if_needed, daemon=True).start()

    port = int(os.environ.get("PORT", "8000"))
    print(f"[hailo-llm] Web UI + proxy listening on 0.0.0.0:{port}")

    # Use waitress (production WSGI server) instead of Flask's dev server.
    # This avoids the "development server" warning and is suitable for the addon.
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port, threads=4)
    except ImportError:
        # Fallback (should not happen if requirements are installed)
        print("[hailo-llm] waitress not available, falling back to Flask dev server")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

if __name__ == "__main__":
    run()
