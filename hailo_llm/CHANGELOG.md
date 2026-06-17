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