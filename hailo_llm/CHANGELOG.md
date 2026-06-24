## 2.0.43
- Improved cleanup script and docs for cases where new versions (or the addon itself) do not appear in the store or no update is offered. Added more aggressive git clone removal (including /data/addons/git/), ha store reload, supervisor repair, broader uninstall commands.
- Bumped to 2.0.43 (to help force cache invalidation after repo refresh).

## 2.0.42
- Match other Hailo examples: run with full `privileged: true` (instead of selective SYS_RAWIO capabilities list) + protection mode disabled (`apparmor: false`). This aligns container privileges closer to official hailo-ollama Docker usage (`--privileged` + device access) for better VDevice/NPU reliability.
- Bumped to 2.0.42.

## 2.0.41
- "LLM not loaded" fix for chat: automatically prime/load the model using a minimal /api/generate call immediately after pull and before every /api/chat send. This forces the backend to initialize the LLM runtime (HEF + VDevice) so subsequent chat works.
- Cleaned chat payload (removed "options": {}) — oatpp backend is strict; minimal payloads are more reliable (matches the clean curls that reach the binary).
- UI now shows currently loaded models via /api/ps in the Models panel.
- Bumped to 2.0.41.

## 2.0.39
- Simplified Dockerfile back to minimal/fast style (like older ~20s builds that worked): removed all verification/echo/set -ex blocks. Uses simple chained `dpkg || true && apt install -f && ldconfig` with cleanup. Dropped unused base packages (gnupg, setuptools, virtualenv) for smaller layer.
- Bumped to 2.0.39.

## 2.0.38
- Improved Dockerfile build reliability and observability for HA Supervisor builds (especially on Pi 5): added numbered progress steps (`>>> [1/5]` etc), `set -ex` tracing, `dpkg ... || true` + `apt-get install -f` pattern, lighter `hailo-ollama --version` verification (replaced heavier `--help > /dev/null` + fatal block with ls). Full /tmp/packages cleanup. The .whl is left in packages/ but not installed (intentional; not in requirements).
- Bumped to 2.0.38.

## 2.0.37
- Updated all HA CLI references from `ha addon` to `ha app` (supervisor command was updated in recent versions).
- Bumped to 2.0.37.

## 2.0.36
- Removed deprecated `build.yaml` (HA Supervisor now warns about it; build params are in Dockerfile).
- Cleaned `config.yaml`: removed `full_access: true` (was conflicting with explicit `devices:` list, causing supervisor validation warnings). Kept selective `devices` + `privileged` list for minimal access.
- Bumped to 2.0.36.

## 2.0.35
- Hardened Dockerfile: removed forgiving `|| true` on dpkg, added strict `set -e` verification that `hailo-ollama --help` works (build fails loudly on bad .deb install).
- Improved run.sh: added NPU/Device Readiness Summary, host-side process check hints, better "not ready" diagnostics with actionable steps.
- Better error surfacing in server.py `_proxy`: returns structured `hailo_backend_error` JSON for 4xx/5xx from the binary (e.g. VDevice failures).
- Small JS chat UI improvement: detects `hailo_backend_error` and shows hint to check `/api/logs`.
- Bumped to 2.0.35.

## 2.0.34
- Improved device diagnostics in run.sh startup (added host-side check suggestions for VDevice "found: 0" errors).
- Added both HAILO_OLLAMA_VDEVICE_GROUP_ID and HAILO_VDEVICE_GROUP_ID env for better compatibility with sharing.
- Bumped to 2.0.34 to ensure latest changes (including icons, ASCII repo name, privileged list) are visible in HA Add-on Store.
- **To make the addon appear for installation**: Remove the custom repo in HA, run `ha supervisor restart`, re-add https://github.com/bjorngluck/hailo-llm-addon , then refresh.

## 2.0.33
- Bumped version to 2.0.33 to force Home Assistant Add-on Store to detect the update after merge to `main`.
- All previous fixes (nginx crash, VDevice alignment, privileged mode, chat routing, persistence, UI) are included.
- **Important for HAOS users**: After pushing, refresh the custom repository in the Add-on Store or use **Rebuild** on the installed addon (see DOCS.md for exact steps).

## 2.0.32
- Nginx routing fix: explicitly route /api/chats*, /health, /api/logs, /api/debug/*, /api/ui/* to the Flask layer (these were previously going to be stolen by the broad /api/ proxy to the binary, breaking chat persistence and debug endpoints). Longest-prefix locations ensure custom paths reach Flask while real ollama /api/* still hit the binary directly.
- Bumped to 2.0.32.

## 2.0.31
- Fixed critical startup crash: nginx config now includes required `events {}` + `http { server {} }` wrapper (bare `server {}` at top level was invalid for `nginx -c`). Addon no longer loops restarting.
- Aligned VDevice sharing env exactly to maintainers' hailo_model_zoo_genai USAGE.rst: `HAILO_OLLAMA_VDEVICE_GROUP_ID=HAILO_OLLAMA_SHARED` (removed non-standard bare `HAILO_VDEVICE_GROUP_ID`).
- Run container as fully `privileged: true` (plus explicit devices) to more closely match official hailo docker examples that use `--device /dev/h1x-0`.
- Kept nginx fronting on 8000 + Flask on 5000 design so exposed port 8000 serves both custom UI and direct-like /api/* from the binary (closer to "hailo-ollama listening on 8000").
- Bumped to 2.0.31.

## 2.0.30
- Improved container launch in run.sh: use nohup + redirect + tail (instead of pipe to tee) to avoid potential interference with hailo-ollama VDevice creation.
- Set both HAILO_VDEVICE_GROUP_ID=SHARED and HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED (matching community examples for sharing).
- Removed unused hailort python wheel from Dockerfile (possible side effects in container).
- Bumped to 2.0.30.

## 2.0.29
- Added /api/debug/device endpoint (and updated docs) to allow on-demand checking of processes holding /dev/hailo0 during troubleshooting (useful when inference fails with vdevice errors even if startup shows clean).
- Bumped to 2.0.29.

## 2.0.28
- Improved device usage diagnostic in run.sh to use /proc directly (portable, no dependency on fuser command) for better debugging of vdevice/Hailo device contention at startup.
- Bumped to 2.0.28.

## 2.0.27
- Added startup diagnostic in run.sh to log current users of /dev/hailo0 (via fuser) to help debug vdevice contention issues.
- Bumped to 2.0.27.

## 2.0.26
- Diagnosis from user-provided logs: HailoRT device allocation error (HAILO_OUT_OF_PHYSICAL_DEVICES) when loading model for inference. The HEF blob path is found correctly, but vdevice creation fails.
- Fix: Set HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED in run.sh (as recommended by hailo_model_zoo_genai) to allow device sharing.
- Improved /api/logs to strip ANSI color codes for cleaner output.
- Bumped to 2.0.26.

## 2.0.25
- Added `/api/logs` endpoint (and updated /health) that returns the last ~100 lines of the hailo-ollama backend log. Makes troubleshooting much easier without needing to exec into the container.
- Bumped to 2.0.25.

## 2.0.24
- Troubleshooting improvements for persistent chat issues:
  - hailo-ollama backend logs now written to `/data/hailo-ollama.log` (accessible location) + teed to addon logs.
  - Added comprehensive set of test `curl` commands in DOCS.md to isolate backend vs UI/ingress problems (non-stream, streaming, health, models, persistence APIs).
  - Updated readiness checks and docs to point at the new log location.
- Bumped to 2.0.24.

## 2.0.23
- Bump to force HA store to detect new version after merge to main. Upgrade button should now offer the new release.
- All previous fixes from 2.0.22 included (chat tracing, history titles, optimistic renders, robust /api/chat handling).

## 2.0.22
- Chat: major robustness and visibility improvements
  - Deep tracing added (browser console `[send]`, `[render]`, chunk logs + server `[chats]` logs in addon logs) so submit/response flow can be followed exactly.
  - History sidebar now shows useful titles (derived from first user message) + message counts instead of always "New chat".
  - Messages render optimistically: user message and "Thinking..." appear immediately (persistence no longer blocks display).
  - `/api/chat` switched to `stream: true` + NDJSON reader (matching working pull path) with full JSON fallback for reliable responses through the Flask proxy and HA ingress.
- Bumped to 2.0.22.

## 2.0.21
- Chat fixes: 
  - Input now always clears on submit.
  - User message now always appears (local fallback chat object if /api/chats fetch temporarily fails).
  - Switched /api/chat call to `stream: false` + `res.json()` for reliable full response delivery (avoids NDJSON streaming buffering issues through proxy + ingress).
  - Assistant response (or clear error) should now appear in the window.
- Upgrade detection improved via repository.yaml + build.yaml + Rebuild instructions.
- Added deep tracing:
  - Server: `[chats]` logs on every create/load/save/list (visible in addon logs).
  - Client: verbose `[send]`, `[createNewChat]`, `[fetchChat]`, `[save...]`, `[renderMessages]`, chunk logs in browser DevTools console.
- History sidebar ("history window"): now derives a title from the submitted user message (first ~48 chars). List items also show message count. Submitting text now visibly creates/updates an entry in the chat list.
- Optimistic UI updates: user message bubble + assistant stub ("Thinking...") are rendered locally immediately. Saves to /api/chats and refreshChatList happen async and never block display or abort generation.
- /api/chat now sends `stream: true` + uses NDJSON line reader (exact pattern proven for /api/pull) + falls back to full res.json(). Handles whatever hailo-ollama + proxy returns. Live token accumulation + re-render.
- saveChatRemote and refreshChatList are now defensive (no uncaught errors can break send path).
- Research confirmed: hailo-ollama returns Ollama-style NDJSON incremental `{"message":{"content":"..."}}` (and final done:true). Proxy forwards; ingress can affect full non-stream bodies — reader is more reliable.

- Fix: typed message no longer stays in the input box after pressing submit. Input is now cleared immediately after the initial guards (before any `fetchChat` / `createNewChat` that could early-return).
- Added `build.yaml` (following patterns from other Hailo-10H addons) to help with builds and version detection in the HA addon store.
- Upgrade button greyed out: For custom Git-based repositories, after pulling a new version the reliable way to get the update is usually the **Rebuild** action (three-dots menu on the installed addon) rather than the store "Update" button. Added instructions.
- Bumped to 2.0.21.

## 2.0.20
- Chat fix: messages sent from UI now receive and display assistant responses.
  - Switched sendMessage to use `stream: true` + NDJSON body reader (same pattern as the working /api/pull handler) to accumulate incremental tokens reliably.
  - The previous `stream: false` + single `res.json()` path was not producing visible responses (likely due to proxy/ingress interaction with non-stream replies).
  - Assistant stub is still created early + persisted; tokens are appended live and re-rendered (with streaming cursor).
  - Keeps the early user message save + robust error paths.
- Bumped to 2.0.20.

## 2.0.19
- **Fixed model persistence root cause.** Validated against https://github.com/hailo-ai/hailo_model_zoo_genai source:
  - HEF blobs are written by BlobResourceProvider to `<data_home>/hailo-ollama/models/blob/sha256_<hash>` (note singular "blob").
  - `data_home()` = `$XDG_DATA_HOME` (if set) else `$HOME/.local/share`. `OLLAMA_MODELS` is **ignored**.
  - Manifests are package-installed to `/usr/share/hailo-ollama/models/manifests/` and discovered at runtime.
- run.sh: set `XDG_DATA_HOME=/media/hailo_llm`, mkdir correct `.../blob` dir, stopped destructive `rm -rf /usr/share/hailo-ollama` (preserves package manifests), launch with correct env, updated diagnostics.
- server.py: updated MODELS_DIR and docs to the real blob location.
- Bumped to 2.0.19.

## 2.0.18
- Unified model storage under /media/hailo_llm/hailo-ollama/models (blobs + manifests) so the binary's HEF files are written to the same persistent tree as the manifests. OLLAMA_MODELS now points there.
- Added explicit inline styles and stronger CSS for the Models button, sidebar minimise (☰), and delete chat icons to force visible theme colors instead of white.
- Cleaned up run.sh duplication in persistence setup.
- Bumped to 2.0.18.

## 2.0.17
- config.yaml map updated to "media:rw" + addon_config etc to match Frigate-H10 example for reliable rw access to /media.
- Switched chat send to stream:false + direct JSON parse for reliable full response (streaming was often empty or not producing assistant content due to proxy/NDJSON issues).
- Fixed secondary icon buttons (top "Models", sidebar minimise ☰, delete chat trash) still appearing white/invisible: added stronger !important color rules for .text-zinc-* and fa-solid in those buttons to ensure theme colors (light gray + accent) are used on dark backgrounds.
- Bumped to 2.0.17.

## 2.0.16
- Switch model storage to /media/hailo_llm (following Frigate-H10 addon pattern).
  - OLLAMA_MODELS and hailo-ollama (manifests + HEF files) now live under /media/hailo_llm/models and /media/hailo_llm/hailo-ollama
  - On HAOS host these are directly at /media/hailo_llm/ (much easier to inspect via Samba/Filebrowser than /mnt/data)
  - Keeps /data/chats for chat history
  - Updated run.sh paths, symlinks, exports, logging, and server.py reporting
- Bumped to 2.0.16.

## 2.0.15
- Persistence: stronger setup in run.sh — always merge (no-clobber) latest package manifests, additional persistent symlinks for common HEF/cache locations (/root/.cache/hailo*, /var/lib/hailo-ollama), explicit OLLAMA_MODELS on the serve command line, chmod a+w like the deb postinst, expanded startup diagnostics (now logs cache + var/lib too). This should ensure both manifests and the actual model (HEF by hash) files survive restarts when written during /api/pull.
- Buttons: root cause was missing CSS rules for .bg-indigo-600 / .bg-rose-600 (and active/hover variants) — only hovers and zinc bgs were defined, so primary buttons had no (or default white) background making white icons invisible or "still white". Added full base background rules + reinforced in the primary selector.
- Chat: always create + persist assistant stub immediately after user message (before the /api/chat call). On any failure or empty stream we now still save a turn with a diagnostic message. Added console.log for response status and every parsed chunk so you can inspect in DevTools exactly what hailo-ollama /api/chat returns. Uses slice to avoid sending the stub in the prompt.
- Bumped to 2.0.15.

## 2.0.14
- Persistence: strengthened run.sh — always mkdir the manifests tree under /data/hailo-ollama, seed package manifests into /data on first/missing, improved logging of /data/models + /data/hailo-ollama contents at startup, cleaner exports + symlinks for OLLAMA_MODELS. Follows official HA /data volume guidance.
- Buttons/icons: consolidated .fa-solid (inherit + explicit size), added text-white + stronger color rules for indigo primary buttons, improved toggle (☰), Models button, Pull, Save, New chat, trash delete, submit (paper plane) visibility and contrast. No more missing or hover-only icons.
- Chat responses: major robustness in sendMessage — tolerant token extractor (message.content / content / response / delta / error), push+persist assistant stub *immediately* after request succeeds (so restarts mid-reply don't lose the turn), always final + error-path saveChatRemote, better error surfacing inside the thread. Chats should now receive and persist assistant replies.
- Bumped version to 2.0.14.

## 2.0.13
- Made available/recommended model buttons wrap properly inside the Models box using flex-wrap, max-width, and ellipsis on chips.
- Fixed icon visibility on buttons: added .fa-solid color inherit/white, and specific unicode for trash, check, times, redo, copy. Submit, Models (download), delete, X, save, menu toggle icons now visible.
- Persistence: improved run.sh to copy package's /usr/share/hailo-ollama to /data/hailo-ollama on first run (if not present), then symlink. This makes manifests and model metadata persistent under /data (HA best practice). Combined with OLLAMA_MODELS=/data/models .
- Bumped version to 2.0.13.

## 2.0.12
- Fixed manifest directory error by removing destructive `rm -rf /usr/share/hailo-ollama/models` (which was deleting the package's installed manifests in models/manifests/). Now preserve the package dir and only symlink user model storage locations.
- Ensured all text (including message textarea, buttons, etc.) is light color (#e4e4e7) via explicit CSS rules for inputs, textareas, buttons.
- Bumped version to 2.0.12.

## 2.0.11
- Fixed hailo-ollama startup crash: "Failed to find manifest directory: hailo-ollama directory not found" (followed by abort/core dump). Added explicit `mkdir -p` for required manifest directories (`/usr/share/hailo-ollama`, `/usr/share/hailo-ollama/manifests`, `/root/.hailo-ollama`, `/opt/hailo-ollama`, etc.) before symlinks and binary start. This ensures the package's manifest dir is present at runtime.
- Cleaned up model persistence setup in run.sh (stronger dir creation, cleanup of stale locations, reinforced OLLAMA_MODELS and symlinks).
- Bumped version to 2.0.11.

## 2.0.10
- Sidebar is now collapsible via ☰ button (and auto-collapses on small screens <768px) to fix mobile layout taking too much space.
- Enhanced model persistence: more aggressive cleanup of stale non-persistent model dirs, explicit OLLAMA_MODELS export, and permission fixes in run.sh.
- Ensured light text color (#e4e4e7) for chat bubbles, assistant text, sidebar buttons, and new chat button.
- Improved model download progress: now uses a single status line + progress bar instead of appending every % as a new line.
- Query for available models: renderCuratedModels now tries to fetch from /hailo/v1/list (falls back to curated) to show only/query available models for the zoo.
- Chat window updates: added explicit CSS for #chat-messages and #main-content to ensure proper flex layout, scrolling, and visibility of messages even without full Tailwind. Messages should now render in the thread with server feedback (streaming).
- Bumped version to 2.0.10.

## 2.0.9
- Fix: When creating new chats (including auto-created and on first message), ensure the `model` field is populated from the currently selected model (via selector or currentModel). Previously some chats were saved with empty "model": "".
- Updated createNewChat and sendMessage to explicitly set and save the model on the chat object.
- Bumped version to 2.0.9.

## 2.0.8
- Made modal show/hide use direct style.display = 'flex'/'none' instead of relying only on classList + CSS. This makes the Models panel (and any modals) work reliably even if some Tailwind classes are not applied.
- Updated initial HTML for model-modal to have style="display: none;" explicitly.
- Bumped version to 2.0.8.

## 2.0.7
- Made API calls robust for HA ingress by introducing explicit INGRESS_BASE using window.location.pathname. All fetch() for api/* and health now construct the correct path under the ingress token (e.g. /api/hassio_ingress/<token>/api/tags). This ensures they are properly proxied by the supervisor to the addon on internal port 8000 instead of hitting HA's root API on 443 (which was causing the persistent 404s).
- CDN completely removed in previous (self-contained CSS); this version solidifies the relative/ingress-safe fetching.
- Bumped version to 2.0.7.

## 2.0.6
- Fixed API calls in the web UI: changed from root-absolute paths (`/api/tags`, `/api/chats`, `/health`) to path-relative (`api/tags`, etc.). This ensures requests go through Home Assistant's ingress proxy (under `/api/hassio_ingress/...`) to the addon's internal port 8000 instead of hitting HA core's `/api` on port 443 (which caused 404s).
- Removed all external CDN dependencies (Tailwind CSS from `https://cdn.tailwindcss.com` and Font Awesome) that were causing network/connection failures in the HA environment (no internet, CSP, or ingress restrictions).
- Replaced with fully self-contained CSS in the HTML `<style>` block providing all necessary dark theme, layout, components, and icon fallbacks (Unicode/emoji). UI is now fully offline-compatible and works reliably via ingress.
- Bumped version to 2.0.6.

## 2.0.5
- UI fixes: Integrated settings section directly into the Models panel for cleaner layout (no more separate broken modal or overlapping content).
- Removed the gear icon and old settings modal (settings now live inside Models).
- Fixed double down-arrow on model selector with proper CSS (appearance: none).
- Softer "Backend starting" message instead of hard "Health check failed".
- Better placeholder in model selector when no models ("— pull a model first —" and disabled).
- Models panel auto-opens on first load (from previous).
- Bumped version to 2.0.5.

## 2.0.4
- UI improvement: Models panel now automatically opens on first load for better discoverability (no need to click "Models" button initially).
- Minor polish for initial user experience.

## 2.0.3
- **Bugfix**: Fixed port conflict on 8000 ("Address already in use"). The `hailo-ollama` binary (v5.3+) primarily respects the `OLLAMA_HOST` environment variable rather than (or in addition to) `--host`/`--port` CLI flags. Now exports `OLLAMA_HOST=127.0.0.1:11434` before launching the binary internally.
- Switched the web server from Flask's development server to `waitress` (production WSGI) to eliminate the "This is a development server" warning.
- Added `waitress` to `requirements.txt`.
- Improved diagnostics: on binary readiness timeout, now prints the last 30 lines of `/tmp/hailo-ollama.log`.
- Bumped version to 2.0.3.

## 2.0.2
- **Bugfix**: Fixed `ModuleNotFoundError: No module named 'flask'` (and missing `requests`). The Dockerfile did not install the Python dependencies listed in `requirements.txt`. Originally the Python server was never executed (the binary was exec'd directly), so the pip step was missing. Added `pip3 install -r /opt/hailo_llm/requirements.txt` after copying rootfs (with `|| true` to match existing install style). This was the root cause of the UI not rendering properly (downloadfile-bin symptom).
- Bumped version to 2.0.2.

## 2.0.1
- **Bugfix**: Web UI now renders correctly when accessed via Home Assistant ingress. Previously the browser would download the response as "downloadfile-bin" instead of showing the chat interface. Fixed by registering a robust catch-all route (after all API proxy routes) so the single-page UI is served for the root and any non-API paths that ingress may forward.
- Documentation fixes: Corrected Mermaid diagram syntax in `docs/architecture.md` so the system diagram, startup sequence, and model download flow now render properly on GitHub.
- Added logging in `serve_ui` to help debug ingress path handling.
- Bumped version to 2.0.1.

## 2.0.0
- **Major feature release**: Persistent model storage on HAOS (/data) — models now survive service restarts and HAOS reboots.
- New built-in modern interactive chat UI (OpenWebUI-inspired) served directly at the ingress:
  - Model selector + dedicated Models manager.
  - Curated one-click downloads for Hailo-optimized models + free-text model pull with live progress.
  - Full chat experience: conversation history (server-persisted), streaming responses, regenerate, copy, edit, stop.
  - Sidebar with chat management (new/rename/delete), modern dark design, keyboard friendly.
- Architecture change: hailo-ollama runs internally; Python layer (Flask) provides the UI + thin transparent proxy so the Ollama-compatible API surface remains available on the same port.
- `auto_download_model` option is now honored (triggers pull of a default recommended model on first start).
- Improved run.sh with readiness checks, better logging, and proper background process management.

## 1.0.0
- Initial release