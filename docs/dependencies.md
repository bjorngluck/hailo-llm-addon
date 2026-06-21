# Dependencies

This document lists all dependencies of the Hailo LLM addon, grouped by layer, with versions (where pinned) and rationale.

## Container Build Dependencies (Dockerfile)

**Base Image**
- `ghcr.io/home-assistant/aarch64-base-debian:bookworm`
  - Provides a minimal, officially supported Debian environment for aarch64 Home Assistant addons.
  - Includes tini (used as ENTRYPOINT for proper signal handling).

**System Packages (apt)**
- `ca-certificates`, `curl`, `gnupg` — downloading and verifying packages
- `python3`, `python3-pip`, `python3-dev`, `python3-setuptools`, `python3-virtualenv` — runtime for the UI/proxy layer
- `libusb-1.0-0` — required by Hailo runtime for USB/PCIe device communication
- `jq` — parsing `/data/options.json` in `run.sh`
- `tini` — (already in base) lightweight init for zombie reaping and signal forwarding

**Hailo Official Packages** (installed from vendored `.deb` and `.whl` in `packages/`)
- `hailort_5.3.0_arm64.deb` — Hailo Runtime (HailoRT). Low-level driver and API for the Hailo-10H NPU.
- `hailo_gen_ai_model_zoo_5.3.0_arm64.deb` — Provides the `hailo-ollama` binary (the core inference server) and pre-compiled HEF models / conversion tools.
- `hailort-5.3.0-cp311-cp311-linux_aarch64.whl` — Python bindings for HailoRT (installed even though the current implementation primarily uses the binary; kept for future extensibility or tooling).

**Cleanup**
- After installation the temporary package files are removed to keep the image small.

## Runtime Python Dependencies (requirements.txt)

Installed with `--break-system-packages` inside the Debian image.

| Package   | Version | Purpose |
|-----------|---------|---------|
| `flask`   | latest  | Lightweight web framework. Serves the chat UI at `/` and implements the transparent API proxy. |
| `requests`| latest  | Used by the proxy to forward requests (including streaming responses) to the internal `hailo-ollama` process. |
| `numpy`   | latest  | Declared in requirements (carried over from earlier versions). Currently lightly used; kept for potential future use with model post-processing or metrics. |

## The Inference Engine (not a pip package)

- `hailo-ollama` binary (from the GenAI Model Zoo deb)
  - Written in C++ on top of HailoRT.
  - Exposes an **Ollama-compatible** REST API (`/api/chat`, `/api/pull`, `/api/tags`, etc.).
  - Uses HEF (Hailo Executable Format) models rather than GGUF.
  - Model storage behavior is influenced by `OLLAMA_MODELS` and several legacy paths (hence the symlinks in `run.sh`).

## Hardware / External Dependencies

- **Hailo AI HAT+ 2** (or any Hailo-10H compatible accelerator) — the actual NPU.
  - Must appear as `/dev/hailo0` inside the container.
  - Requires privileged mode + `SYS_RAWIO` capability (configured in `config.yaml`).
- **HAOS Supervisor** — provides:
  - The `/data` persistent volume
  - Ingress reverse proxy (port 8000)
  - Addon configuration (`options.json`)
- **aarch64 CPU** — the addon is built only for aarch64 (Raspberry Pi 5 + HAT is the primary target).

## Why These Choices?

- **Pinned Hailo 5.3.0 stack** — Provides a known-good, tested combination of runtime + model zoo + `hailo-ollama` binary. Upgrades have historically caused model wipes or ABI issues in the community; pinning reduces risk.
- **Flask instead of a heavier framework or separate web server** — Extremely small footprint. The entire UI is delivered as one self-contained HTML page (Tailwind via CDN + vanilla JS). No Node.js build step is required.
- **Proxy pattern** — Keeps us dependent on the official binary for best performance and model compatibility while still allowing us to own the user-facing port for the UI.
- **File-based persistence** — No SQLite or external database. Simple, robust, and perfectly aligned with HA addon `/data` semantics.
- **Minimal Python deps** — Only what is strictly necessary for proxying and serving the UI. `numpy` is the only "extra" carried for historical/future reasons.

## Version Matrix (Current)

- HailoRT: 5.3.0
- hailo_gen_ai_model_zoo: 5.3.0
- Base OS: Debian bookworm (aarch64)
- Python: 3.11 (from the wheel and base image)

When upgrading any of the Hailo packages, the following must be re-validated:
- Binary location and startup behavior
- Model storage paths
- API compatibility (`/api/pull` and streaming `/api/chat`)
- Device access and performance

## Development / Testing Dependencies

None are declared in the repository (no `requirements-dev.txt`). Typical local workflow:

- Edit on any machine
- Build the addon inside a HA dev environment or using `ha app build`
- Test on real aarch64 hardware with a physical Hailo HAT (the binary and NPU access cannot be easily emulated)

## Image Size Considerations

The vendored `.deb` and `.whl` files are the largest contributors. After installation they are removed from the final layer. The resulting image stays reasonably small for an edge AI addon.

## License Notes

- Hailo packages are provided under Hailo's own license terms (check the `.deb` files or Hailo documentation).
- The addon glue code (run.sh, server.py, documentation) is MIT (or the license declared at the repository root).

If you add new runtime dependencies, please update this file and the root README.
