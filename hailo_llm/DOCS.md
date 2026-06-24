# Hailo LLM Documentation

## What's new in 2.0
- Models are now **persistently stored** under `/data` inside the addon. Downloaded models survive `ha app restart` and full HAOS reboots.
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

- Your latest version bump (e.g. 2.0.37) and changes must be present on `main` (not just a feature branch like `model-storage-and-interactive-feature`).
- After pushing to `main`, refresh the repo in the store (see above).
- For active development on a feature branch, the most reliable method is to update your source, then on the installed **Hailo LLM** add-on page use the **⋯** menu → **Rebuild**.

We provide both `repository.json` and `repository.yaml` for maximum compatibility with the Home Assistant addon store.

**Note on build configuration:** We no longer use `build.yaml` (it is deprecated by Home Assistant Supervisor). All build parameters are now in the `Dockerfile` directly.

## Troubleshooting Install & Build Issues

If the addon does not appear in the store after adding the repo, or the build/install fails repeatedly:

1. **Remove the repository** from Add-ons → Store → ⋮ → Repositories.
2. Run the cleanup script (recommended):
   ```bash
   # Download and run the helper (or copy from docs/hailo_cleanup.sh in the repo)
   curl -O https://raw.githubusercontent.com/bjorngluck/hailo-llm-addon/main/docs/hailo_cleanup.sh
   bash hailo_cleanup.sh
   ```
   (The script removes old git clones, uninstalls variants, prunes docker images, and restarts supervisor.)
3. Wait 60s, re-add the repo: `https://github.com/bjorngluck/hailo-llm-addon`
4. Hard refresh browser.
5. After the script:
   ```bash
   # Check status
   ha app list | grep -i hailo

   # Try updating (as recommended by supervisor)
   ha app update hailo_llm || true
   ha app update local_hailo_llm || true
   ha app update 7d290ede_hailo_llm || true

   # If needed, clean build + install:
   # ha app build --no-cache local_hailo_llm
   # ha app install local_hailo_llm
   ```

Common causes:
- Old cached git clone in `/data/apps/git/`
- Deprecated `build.yaml` (we removed it in v2.0.37+)
- Config conflict between `full_access: true` and explicit `devices:` (fixed in v2.0.37+)
- Supervisor state corruption from previous failed builds

After install, check the addon logs for the "NPU / Device Readiness Summary".

## Troubleshooting Chat / API Issues

### 1. Hailo-ollama logs (the real backend)
- Logs are written to `/data/hailo-ollama.log` inside the addon (persistent and host-accessible).
- How to view:
  - Install the community "Filebrowser" or "Studio Code Server" addon and browse the addon's data (or /media if you map it).
  - From Terminal & SSH addon (or SSH to HA): `docker exec -it addon_hailo_llm tail -f /data/hailo-ollama.log` (container name is usually `addon_hailo_llm` or check `ha app info hailo_llm`).
  - In the addon logs (Settings → Add-ons → Hailo LLM → Log) you will also see some output because we tee the logs.
- The startup script also dumps the last 30 lines if the backend doesn't become ready.

### 2. Test curl commands (bypass UI / ingress buffering issues)

**Best way to rule out the proxy / nginx / ingress / custom UI entirely:**

Since v2.0.39+ the native `hailo-ollama` binds to `0.0.0.0:11434`.

1. In the addon page → **Network** tab, make sure a host port is mapped for 11434 (e.g. `11434` → container `11434`).
2. Use the **native** address for testing:

```bash
# Use the host-mapped native port (bypasses nginx + Flask + HA ingress completely)
HOST=http://YOUR-HA-IP:11434

# Basic list
curl -s $HOST/api/tags | jq

# Simple non-streaming chat — easiest for debugging "no usable response"
curl -s -X POST $HOST/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:1.5b",
    "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
    "stream": false
  }' | jq

# Streaming chat (raw NDJSON)
curl -N --no-buffer -s -X POST $HOST/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:1.5b",
    "messages": [{"role": "user", "content": "Count to 3 slowly."}],
    "stream": true
  }' | while IFS= read -r line; do
    if [ -n "$line" ]; then echo "$line"; fi
  done
```

If the **direct** curls to `:11434` return proper responses/tokens but the in-UI chat (on port 8000) does not, then the problem is in the nginx proxy, HA ingress, or the JavaScript streaming reader in the UI.

If direct `:11434` chat also gives empty / bad responses, the issue is in hailo-ollama itself (check `/data/hailo-ollama.log` or VDevice during generation).

---

**Other curls (via the normal addon port 8000 / ingress — still useful)**

**Prerequisites**
- Expose port 8000 (or use the ingress URL).
- Set `HOST=http://YOUR-HA-IP:8000` (the proxied surface).

```bash
# 1. Basic health (addon proxy + backend reachability via 8000)
curl -s $HOST/health | jq

# 2. List models (via the proxied surface)
curl -s $HOST/api/tags | jq

# 3. UI chat persistence (Flask only)
curl -s $HOST/api/chats | jq

# 4. Hailo backend logs
curl -s $HOST/api/logs | jq -r .log

# 5. Device holders check (after a bad chat response)
curl -s $HOST/api/debug/device | jq
```

**Direct backend test (from inside the container — always uses native 11434)**
```bash
docker exec -it addon_hailo_llm curl -s http://127.0.0.1:11434/api/tags | jq

# Direct non-stream chat test bypassing everything
docker exec -it addon_hailo_llm curl -s -X POST http://127.0.0.1:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:1.5b","messages":[{"role":"user","content":"hi"}],"stream":false}' | jq
```

### How to interpret results

- **Direct curls on :11434 give good tokens** but UI chat (8000) does not → problem is nginx proxy, HA ingress buffering, or the JS reader in the embedded UI (`server.py`).
- **Direct :11434 chat also gives empty / no usable response** → problem is in `hailo-ollama` (look at `/data/hailo-ollama.log` for generation/VDevice errors during the `/api/chat` call).
- `/api/tags` and `/api/pull` work but chat does not → chat-specific response format difference or generation issue on the model.

### 3. Other quick checks
- Make sure a model is pulled (use the Models button in UI or the pull curl above).
- `curl -s $HOST/health` should show `"backend_reachable": true`
- For streaming problems through ingress: non-stream (`stream:false`) often works better for debugging.