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

## Updating the add-on

After you `git pull` (or pull new commits) in this repository:

1. In Home Assistant, go to **Settings → Add-ons → Hailo LLM**.
2. Click the **⋯** (three dots) in the top right of the add-on page.
3. Choose **Rebuild**.

**Rebuild** is the most reliable way to pick up source changes when using a Git-based custom repository.

The "Update" button in the Add-on Store can sometimes be greyed out because:
- HA has cached the previous repository metadata.
- For local/Git add-ons the store "Update" detection is not always immediate.
- Version comparison uses the `version` field in `config.yaml`.

To force the store to see the new version (when the upgrade button only shows the current/old version):
1. Add-ons → Add-on Store → ⋮ (top right) → Repositories.
2. Click the refresh icon (circular arrows) next to your "Bjorngluck Hailo Add-ons" repository.
3. If still not showing, remove the repository completely, then re-add it using the exact URL: `https://github.com/bjorngluck/hailo-llm-addon`
4. Wait 30 seconds, then hard-refresh your browser (Ctrl+Shift+R).
5. On the installed Hailo LLM addon page, use the **⋯** menu → **Rebuild** (this often works even when the store "Update" button is grey or only shows the current version).
6. As a last resort: restart the Supervisor (`ha supervisor restart` in SSH or Terminal addon) or restart Home Assistant entirely.

**Critical for Git-based repos:** Home Assistant's Add-on Store always clones the repository's **default branch** (currently `main` for this repo). 

- Your latest version bump (e.g. 2.0.33) and changes must be present on `main` (not just a feature branch like `model-storage-and-interactive-feature`).
- After pushing to `main`, refresh the repo in the store (see above).
- For active development on a feature branch, the most reliable method is to update your source, then on the installed **Hailo LLM** add-on page use the **⋯** menu → **Rebuild**.

We also ship a `build.yaml` (matching patterns used by other Hailo-10H add-ons) to improve build compatibility.

We provide both `repository.json` and `repository.yaml` for maximum compatibility with the Home Assistant addon store.

## Troubleshooting Chat / API Issues

### 1. Hailo-ollama logs (the real backend)
- Logs are written to `/data/hailo-ollama.log` inside the addon (persistent and host-accessible).
- How to view:
  - Install the community "Filebrowser" or "Studio Code Server" addon and browse the addon's data (or /media if you map it).
  - From Terminal & SSH addon (or SSH to HA): `docker exec -it addon_hailo_llm tail -f /data/hailo-ollama.log` (container name is usually `addon_hailo_llm` or check `ha addons info hailo_llm`).
  - In the addon logs (Settings → Add-ons → Hailo LLM → Log) you will also see some output because we tee the logs.
- The startup script also dumps the last 30 lines if the backend doesn't become ready.

### 2. Test curl commands (bypass UI / ingress buffering issues)
Use these to verify the backend works independently of the web UI, HA ingress, or the Flask proxy.

**Prerequisites**
- Expose port 8000 on the addon (in the addon config → Network → 8000/tcp → 8000) or use the host IP where the addon is running.
- Set `HOST=http://YOUR-HA-IP:8000` (or localhost if testing from inside HA).

```bash
# 1. Basic health (addon proxy + backend reachability)
curl -s $HOST/health | jq

# 2. List available models (proxied to hailo-ollama)
curl -s $HOST/api/tags | jq

# 3. List via hailo native endpoint
curl -s $HOST/hailo/v1/list | jq

# 4. Simple non-streaming chat (easiest for debugging full response)
curl -s -X POST $HOST/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:1.5b",
    "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
    "stream": false
  }' | jq

# 5. Streaming chat (NDJSON - what the UI uses under the hood)
curl -N --no-buffer -s -X POST $HOST/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:1.5b",
    "messages": [{"role": "user", "content": "Count to 5 slowly."}],
    "stream": true
  }' | while IFS= read -r line; do
    if [ -n "$line" ]; then
      echo "$line" | jq -r '.message.content // .response // empty' 2>/dev/null || echo "$line"
    fi
  done

# 6. Test the UI's chat persistence endpoints (the /api/chats used by the embedded SPA)
curl -s $HOST/api/chats | jq

# 7. Hailo backend logs (last 100 lines) - super useful for troubleshooting chat
curl -s $HOST/api/logs | jq -r .log

# 8. Device holders check (call this right after a failed chat)
curl -s $HOST/api/debug/device | jq
```

**Direct backend test (from inside the container, e.g. via docker exec or Terminal addon)**
```bash
docker exec -it addon_hailo_llm curl -s http://127.0.0.1:11434/api/tags | jq
```

If these curls return proper JSON / tokens but the UI chat is broken, the problem is in the web UI (server.py INDEX_HTML JS) or ingress buffering.

If curls fail or return errors, the issue is with hailo-ollama itself (check /data/hailo-ollama.log) or the proxy in server.py.

### 3. Other quick checks
- Make sure a model is pulled (use the Models button in UI or the pull curl above).
- `curl -s $HOST/health` should show `"backend_reachable": true`
- For streaming problems through ingress: non-stream (`stream:false`) often works better for debugging.