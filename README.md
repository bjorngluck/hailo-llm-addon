# Hailo LLM Add-on

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Addon-blue?logo=home-assistant)](https://www.home-assistant.io/)
[![Architecture](https://img.shields.io/badge/arch-aarch64-green)](https://github.com/bjorngluck/hailo-llm-addon)
[![Version](https://img.shields.io/badge/version-2.0.45-orange)](https://github.com/bjorngluck/hailo-llm-addon/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Hailo-10H Model Zoo + Ollama-compatible LLM server with a beautiful built-in chat UI for Home Assistant.**

This addon turns your Home Assistant into a private, on-device AI assistant powered by the **Hailo AI HAT+ 2** (or compatible Hailo-10H hardware). It provides a fast, local LLM experience that feels like a self-hosted Ollama instance — but with a first-class interactive web interface included.

> **New in v2.0**: Models and chat history are now **persistently stored** on HAOS (survive reboots and addon restarts) + a modern, OpenWebUI-inspired chat experience is built directly into the addon.

## ✨ Features

- **Interactive Chat UI** (served at the ingress)
  - Sidebar with persistent conversation history (new chat, rename, delete, switch)
  - Model selector + dedicated Models manager
  - Curated one-click downloads for Hailo-optimized models + free-text model pull with live progress
  - Streaming responses, regenerate last answer, copy messages, edit & resend, stop generation
  - Modern dark design with keyboard support (Enter to send, Shift+Enter for newline)
- **Persistent Storage**
  - Downloaded models survive `ha app restart` and full HAOS reboots
  - Chat history is stored server-side on the device
- **Ollama-compatible Backend**
  - Full compatibility with Home Assistant conversation integrations, Open WebUI, and any Ollama client
  - The same port serves both the beautiful UI **and** the raw API (via a lightweight transparent proxy)
- **Easy Model Management**
  - Recommended models for the Hailo-10H (qwen2.5, etc.)
  - Pull any model supported by the Hailo GenAI Model Zoo
  - Auto-download option for a default model on first start
- **Hardware Accelerated**
  - Direct access to the Hailo NPU via the official `hailo-ollama` runtime (C++ on HailoRT)
  - Low latency, efficient inference on the edge

## 📋 Requirements

- Home Assistant OS (recommended) or Container
- **aarch64** architecture (e.g. Raspberry Pi 5, or other supported HA hardware)
- **Hailo AI HAT+ 2** (or compatible Hailo-10H accelerator) with the device appearing as `/dev/hailo0`
- Internet connection for the first model download

## 🚀 Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add this repository URL:
   ```
   https://github.com/bjorngluck/hailo-llm-addon
   ```
3. Install the **Hailo LLM** addon
4. (Optional but recommended) Go to the **Configuration** tab and set:
   - `keep_alive`: `300m` (or longer)
   - `auto_download_model`: `true` (pulls a default model automatically)
5. Start the addon
6. Open the **Hailo LLM** panel (or click the link in the addon info)

## ⚙️ Configuration Options

| Option                | Default   | Description |
|-----------------------|-----------|-------------|
| `keep_alive`          | `300m`    | How long the model stays loaded in memory (e.g. `5m`, `1h`, `-1` for forever). Passed to the backend. |
| `auto_download_model` | `false`   | If true, automatically downloads a recommended default model the first time the addon starts with no models present. |

## 💬 The Chat Interface

The UI is served directly at the root of the ingress (no extra containers or add-ons required).

**Main areas:**
- **Left sidebar** — List of all your conversations. Create new chats, rename, or delete them. All history is persisted on disk.
- **Top bar** — Current model selector + quick "Models" button.
- **Models manager** (modal) — 
  - See installed models
  - One-click download of curated, well-tested models for the Hailo hardware
  - Free-text field to pull any supported model tag (e.g. `qwen2.5:1.5b`)
  - Live download progress
- **Chat window** — Familiar modern chat experience with streaming, markdown, code blocks, and action buttons (regenerate, copy, edit).
- **Composer** — Type your message. Advanced users can adjust generation parameters in future versions.

The interface is designed to work great inside the Home Assistant sidebar/panel.

## 🔌 Using as an Ollama Backend

The addon exposes a full **Ollama-compatible API** on the same port (8000) that serves the UI.

External tools can connect using the ingress URL or the mapped host port:

- `GET /api/tags` — list installed models
- `POST /api/chat` (stream) — chat completions
- `POST /api/pull` (stream) — download models
- And other standard endpoints (`/api/delete`, etc.)

This works with:
- Home Assistant "Extended OpenAI Conversation" or similar integrations (point them at the addon)
- Another Open WebUI instance (set `OLLAMA_BASE_URL`)
- Any script or tool that speaks the Ollama REST API

The Python layer acts as a thin proxy so you get both the nice UI **and** full API compatibility without port conflicts.

## 🗄️ Model Storage & Persistence

Models are stored in `/data/models` inside the addon container. This directory is mapped to persistent storage on your HAOS host.

- Models survive addon restarts and HAOS reboots
- Chat conversations are stored as JSON in `/data/chats`
- On upgrade of the Hailo GenAI Model Zoo package, your user-pulled models are protected (unlike some bare-metal setups)

You can inspect the files by opening a terminal into the running addon container if needed.

## 🛠️ Troubleshooting

**No Hailo device detected**
- Make sure the HAT is properly seated and powered
- Check `ha host hardware` or `ls /dev/hailo*` inside the addon
- The addon requires `privileged: true` and device passthrough (already configured)

**First model download is slow / fails**
- Ensure the addon has internet access
- Large models can take 5–30+ minutes depending on your connection
- Check the "Models" manager for live progress

**API clients can't connect**
- Use the full ingress URL (including the path if you changed the entry)
- The API is available at the root (same as the UI)
- Try `curl http://homeassistant.local:8123/api/hassio_ingress/<your-slug>/api/tags`

**Models disappear after restart**
- This should no longer happen in v2.0+. If it does, open an issue with addon logs.

View detailed logs in the addon UI or via `ha app logs hailo_llm`.

## 📚 Documentation

- [Architectural Overview & Diagrams](docs/architecture.md)
- [Dependencies](docs/dependencies.md)
- Internal technical docs are also kept in `hailo_llm/DOCS.md`

## 🤝 Contributing

Contributions are welcome!

1. Fork the repo
2. Create a feature branch (`git checkout -b my-feature`)
3. Make your changes (see the `/docs` folder for architecture notes)
4. Test on real hardware if possible
5. Open a Pull Request

Please keep the addon lightweight — the goal is a self-contained experience without pulling in heavy extra containers.

## 📄 License

MIT (see LICENSE file if present in the repo).

## 🙏 Acknowledgments

- [Hailo](https://hailo.ai/) for the incredible Hailo-10H / AI HAT+ 2 accelerator and the GenAI Model Zoo
- The open-source Ollama project for the API inspiration and compatibility target
- The Home Assistant community for the excellent addon framework

---

**Add this repo and start chatting privately on your own hardware today!**

If you find this useful, consider starring the repository ⭐ and sharing your setup.