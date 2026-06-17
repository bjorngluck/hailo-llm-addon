#!/usr/bin/env python3
"""
Hailo LLM Add-on - Web UI + API Proxy (Flask)

- Serves a modern, OpenWebUI-inspired interactive chat experience at the HA ingress (port 8000).
- Provides a thin transparent proxy so the full Ollama-compatible surface (/api/*, /hailo/*)
  remains available on the same port for external clients (HA conversation, curl, etc.).
- Persists downloaded models via the launch script (OLLAMA_MODELS=/data/models + symlinks).
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
MODELS_DIR = os.path.join(DATA_DIR, "models")
CHATS_DIR = os.path.join(DATA_DIR, "chats")
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
    return chats

def load_chat(chat_id: str):
    path = _chat_path(chat_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_chat(chat_data: dict):
    """chat_data must contain at least id, title, model, messages (list), updated."""
    chat_id = chat_data["id"]
    chat_data["updated"] = int(time.time())
    path = _chat_path(chat_id)
    tmp = path + ".tmp"
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
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"/>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&amp;family=Space+Grotesk:wght@500;600&amp;display=swap');
    :root { --accent: #6366f1; }
    body { font-family: 'Inter', system_ui, sans-serif; }
    .font-display { font-family: 'Space Grotesk', 'Inter', sans-serif; }
    .chat-container { scrollbar-width: thin; }
    .message-bubble { max-width: 78%; }
    .assistant-bubble { background: #1f2937; }
    .user-bubble { background: #6366f1; color: white; }
    .streaming::after { content: '▍'; animation: blink 1s step-end infinite; }
    @keyframes blink { 50% { opacity: 0; } }
    .sidebar { transition: transform .2s ease; }
    .modern-card { background: #111827; border: 1px solid #1f2937; }
    .model-chip { transition: all .1s ease; }
    .model-chip:hover { transform: translateY(-1px); box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1); }
    .hailo-glow { box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1); }
    .log-line { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 0.75rem; }
  </style>
</head>
<body class="bg-zinc-950 text-zinc-200">
  <div class="flex h-screen overflow-hidden">
    <!-- Sidebar -->
    <div class="w-72 border-r border-zinc-800 bg-zinc-900 flex flex-col">
      <!-- Header -->
      <div class="p-4 border-b border-zinc-800 flex items-center gap-3">
        <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white">
          <i class="fa-solid fa-microchip text-lg"></i>
        </div>
        <div>
          <div class="font-semibold font-display text-xl tracking-tighter">Hailo LLM</div>
          <div class="text-[10px] text-zinc-500 -mt-0.5">Hailo-10H + Model Zoo</div>
        </div>
      </div>

      <!-- New Chat -->
      <div class="p-3">
        <button onclick="createNewChat()"
                class="w-full flex items-center justify-center gap-2 rounded-2xl bg-zinc-800 hover:bg-zinc-700 active:bg-zinc-900 transition px-4 py-2.5 text-sm font-medium">
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
    <div class="flex-1 flex flex-col min-w-0">
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
                    class="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-2xl border border-zinc-700 hover:bg-zinc-800 active:bg-zinc-900">
              <i class="fa-solid fa-download text-indigo-400"></i>
              <span>Models</span>
            </button>
          </div>
        </div>

        <div class="flex items-center gap-2 text-xs">
          <div class="px-3 py-1 rounded-2xl bg-zinc-800 text-zinc-400 flex items-center gap-1.5">
            <i class="fa-solid fa-bolt text-emerald-400"></i>
            <span>Hailo accelerated</span>
          </div>
          <button onclick="showSettings()" class="px-3 py-1.5 rounded-2xl hover:bg-zinc-800 text-zinc-400">
            <i class="fa-solid fa-cog"></i>
          </button>
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
                    class="h-12 w-12 flex-shrink-0 rounded-3xl bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 transition flex items-center justify-center">
              <i class="fa-solid fa-paper-plane"></i>
            </button>
            <button onclick="stopGeneration()" id="stop-btn"
                    class="hidden h-12 w-12 flex-shrink-0 rounded-3xl bg-rose-600 hover:bg-rose-500 items-center justify-center">
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
  <div id="model-modal" onclick="if (event.target.id === 'model-modal') closeModelManager()" class="hidden fixed inset-0 bg-black/70 flex items-center justify-center z-50">
    <div onclick="event.stopImmediatePropagation()" class="modern-card w-full max-w-lg rounded-3xl p-5 m-4">
      <div class="flex justify-between items-center mb-4">
        <div class="font-semibold text-lg">Models</div>
        <button onclick="closeModelManager()" class="text-zinc-400 hover:text-white"><i class="fa-solid fa-times text-xl"></i></button>
      </div>

      <!-- Installed -->
      <div class="mb-4">
        <div class="uppercase text-xs tracking-wider text-zinc-500 mb-2 px-1">Installed</div>
        <div id="installed-models" class="space-y-1 text-sm"></div>
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
                  class="px-5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-sm font-medium">Pull</button>
        </div>
        <div id="pull-progress" class="mt-3 hidden text-xs log-line bg-zinc-900 border border-zinc-800 rounded-2xl p-2 max-h-24 overflow-auto"></div>
      </div>
    </div>
  </div>

  <!-- Settings -->
  <div id="settings-modal" onclick="if (event.target.id === 'settings-modal') closeSettings()" class="hidden fixed inset-0 bg-black/70 flex items-center justify-center z-50">
    <div onclick="event.stopImmediatePropagation()" class="modern-card w-full max-w-sm rounded-3xl p-5 m-4">
      <div class="font-semibold mb-4">Settings</div>
      <div class="space-y-4 text-sm">
        <div>
          <label class="block text-xs text-zinc-400 mb-1">Keep Alive</label>
          <input id="setting-keep-alive" type="text" class="w-full bg-zinc-900 border border-zinc-700 rounded-2xl px-3 py-2 text-sm" value="300m"/>
          <div class="text-[10px] text-zinc-500 mt-1">e.g. 300m, 1h, -1 (forever)</div>
        </div>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm">Auto-download default model</div>
            <div class="text-xs text-zinc-500">On first start if no models present</div>
          </div>
          <input type="checkbox" id="setting-auto-download" class="accent-indigo-500 w-4 h-4"/>
        </div>
      </div>
      <div class="mt-6 flex justify-end gap-2">
        <button onclick="closeSettings()" class="px-4 py-1.5 rounded-2xl text-sm hover:bg-zinc-800">Close</button>
        <button onclick="saveSettings()" class="px-4 py-1.5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-sm">Save</button>
      </div>
    </div>
  </div>

  <script>
    // ============== Tiny client-side app ==============
    let currentChatId = null;
    let currentModel = "";
    let abortController = null;

    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    function fmtTime(ts) {
      if (!ts) return '';
      const d = new Date(ts * 1000);
      return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
    }

    async function loadModelsIntoSelect() {
      try {
        const res = await fetch('/api/tags');
        const data = await res.json();
        const sel = $('#model-select');
        sel.innerHTML = '';
        const models = (data.models || []).map(m => m.name || m.model).filter(Boolean);
        
        if (models.length === 0) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = '— no models —';
          sel.appendChild(opt);
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
      const res = await fetch('/api/chats/' + chatId);
      if (!res.ok) return null;
      return res.json();
    }

    async function saveChatRemote(chat) {
      await fetch('/api/chats/' + chat.id, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(chat)
      });
      await refreshChatList();
    }

    async function refreshChatList() {
      const res = await fetch('/api/chats');
      const list = await res.json();
      const container = $('#chat-list');
      container.innerHTML = '';
      list.forEach(c => {
        const div = document.createElement('div');
        div.className = `px-3 py-2 rounded-2xl mx-1 mb-1 text-sm cursor-pointer flex justify-between items-center gap-2 hover:bg-zinc-800 ${currentChatId === c.id ? 'bg-zinc-800' : ''}`;
        div.innerHTML = `
          <div class="flex-1 min-w-0" onclick="switchToChat('${c.id}')">
            <div class="truncate font-medium">${c.title || 'Untitled'}</div>
            <div class="text-xs text-zinc-500 truncate">${c.model || ''}</div>
          </div>
          <button onclick="event.stopImmediatePropagation(); deleteChat('${c.id}');" class="text-zinc-500 hover:text-rose-400 p-1"><i class="fa-solid fa-trash text-xs"></i></button>
        `;
        container.appendChild(div);
      });
    }

    function renderMessages(chat) {
      const area = $('#chat-messages');
      area.innerHTML = '';
      $('#empty-state').classList.add('hidden');

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
        inner.innerHTML = content || '<span class="opacity-50">(empty)</span>';

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
      currentChatId = chatId;
      const chat = await fetchChat(chatId);
      if (!chat) return;
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
      const model = preferredModel || currentModel || '';
      const chat = await (await fetch('/api/chats', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ model })
      })).json();
      currentChatId = chat.id;
      currentModel = chat.model || model;
      $('#model-select').value = currentModel;
      $('#composer-model').textContent = currentModel;
      renderMessages(chat);
      await refreshChatList();
      $('#message-input').focus();
    }

    async function deleteChat(chatId) {
      if (!confirm('Delete this conversation?')) return;
      await fetch('/api/chats/' + chatId, { method: 'DELETE' });
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

      if (!currentChatId) {
        await createNewChat();
      }

      let chat = await fetchChat(currentChatId);
      if (!chat) return;

      // append user message
      chat.messages.push({ role: 'user', content: text, ts: Math.floor(Date.now()/1000) });
      await saveChatRemote(chat);
      renderMessages(chat);
      input.value = '';

      // call backend (proxied)
      generationInFlight = true;
      const stopBtn = $('#stop-btn');
      stopBtn.classList.remove('hidden');
      stopBtn.classList.add('flex');

      abortController = new AbortController();

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: currentModel || chat.model,
            messages: chat.messages.map(m => ({ role: m.role, content: m.content })),
            stream: true,
            options: {} // can be extended with temp etc.
          }),
          signal: abortController.signal
        });

        if (!res.ok || !res.body) throw new Error('Chat request failed');

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let assistantMessage = { role: 'assistant', content: '', ts: Math.floor(Date.now()/1000) };
        chat.messages.push(assistantMessage);
        renderMessages(chat);

        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // NDJSON style — one JSON object per line (ollama/hailo format)
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const obj = JSON.parse(line);
              if (obj.message && obj.message.content) {
                assistantMessage.content += obj.message.content;
              }
              // also handle done
              if (obj.done) {
                // final
              }
            } catch (e) { /* ignore partial */ }
          }
          renderMessages(chat);
        }
        // flush remaining buffer
        if (buffer.trim()) {
          try {
            const obj = JSON.parse(buffer);
            if (obj.message && obj.message.content) assistantMessage.content += obj.message.content;
          } catch(e){}
          renderMessages(chat);
        }

        // persist final
        await saveChatRemote(chat);
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error(err);
          alert('Generation error: ' + err.message);
        }
      } finally {
        generationInFlight = false;
        stopBtn.classList.add('hidden');
        stopBtn.classList.remove('flex');
        abortController = null;
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
      $('#model-modal').classList.remove('hidden');
      $('#model-modal').classList.add('flex');
      refreshInstalledModels();
      renderCuratedModels();
      $('#pull-progress').classList.add('hidden');
    }

    function closeModelManager() {
      $('#model-modal').classList.remove('flex');
      $('#model-modal').classList.add('hidden');
      // refresh model list in header
      loadModelsIntoSelect();
    }

    async function refreshInstalledModels() {
      const container = $('#installed-models');
      container.innerHTML = '<div class="text-xs text-zinc-500 px-1 py-1">Loading...</div>';
      try {
        const res = await fetch('/api/tags');
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
            <button class="text-rose-400 hover:text-rose-300 text-xs px-2" onclick="deleteModel('${name}', this)">delete</button>
          `;
          container.appendChild(div);
        });
      } catch (e) {
        container.innerHTML = '<div class="text-xs text-rose-400 px-1">Failed to load installed models</div>';
      }
    }

    function renderCuratedModels() {
      const container = $('#curated-models');
      container.innerHTML = '';
      (window.CURATED || []).forEach(name => {
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
      progress.innerHTML = `<div class="text-emerald-400">Pulling ${name}...</div>`;

      try {
        const res = await fetch('/api/pull', {
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
              if (obj.status) {
                const line = document.createElement('div');
                line.textContent = obj.status + (obj.completed ? ` (${Math.round(obj.completed/obj.total*100)}%)` : '');
                progress.appendChild(line);
                progress.scrollTop = progress.scrollHeight;
              }
            } catch(e){}
          }
        }
        progress.innerHTML += `<div class="text-emerald-400 mt-1">✓ Done</div>`;
        await refreshInstalledModels();
        await loadModelsIntoSelect();
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

    async function deleteModel(name, btn) {
      if (!confirm(`Delete model "${name}"?`)) return;
      btn.textContent = '…';
      try {
        await fetch('/api/delete', {
          method: 'DELETE',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ name })
        });
      } catch(e){}
      await refreshInstalledModels();
      await loadModelsIntoSelect();
    }

    // ---------------- Settings (very light) ----------------
    function showSettings() {
      $('#settings-modal').classList.remove('hidden');
      $('#settings-modal').classList.add('flex');
      // naive: we don't persist keep_alive from here yet (run.sh reads options.json on start)
      // but we can at least show current values
      fetch(OPTIONS_PATH).then(r => r.ok ? r.json() : {}).then(opts => {
        if (opts.keep_alive) $('#setting-keep-alive').value = opts.keep_alive;
        $('#setting-auto-download').checked = !!opts.auto_download_model;
      }).catch(()=>{});
    }
    function closeSettings() {
      $('#settings-modal').classList.remove('flex');
      $('#settings-modal').classList.add('hidden');
    }
    async function saveSettings() {
      // For a real implementation we would write back to /data/options.json
      // For now we just close (user can change via HA UI options)
      alert('Settings are read at addon start from the Home Assistant add-on configuration.\nChange them in the add-on UI and restart the addon.');
      closeSettings();
    }

    // ---------------- Boot ----------------
    window.CURATED = ["qwen2.5:1.5b", "qwen2:1.5b", "phi3:3.8b"];

    async function initUI() {
      // Device status
      try {
        const h = await fetch('/health');
        const data = await h.json();
        const el = $('#device-text');
        if (data.hailo_device) {
          el.innerHTML = `<span class="text-emerald-400">Hailo device ready</span>`;
        } else {
          el.innerHTML = `<span class="text-amber-400">No Hailo device</span>`;
        }
      } catch(e) {
        $('#device-text').textContent = 'Health check failed';
      }

      // Initial model load
      await loadModelsIntoSelect();

      // Chat list + possibly auto-create first chat
      await refreshChatList();

      // If no chats, start one
      const listRes = await fetch('/api/chats');
      const chats = await listRes.json();
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
        "models_persisted_at": MODELS_DIR,
        "chats_persisted_at": CHATS_DIR,
    })

@app.route("/api/ui/recommended-models")
def recommended_models():
    return jsonify({"recommended": get_recommended_models()})

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
