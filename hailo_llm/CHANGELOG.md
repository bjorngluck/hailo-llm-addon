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