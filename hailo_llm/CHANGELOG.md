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