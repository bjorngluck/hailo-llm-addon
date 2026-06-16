# Architecture Overview

This document describes the internal architecture of the Hailo LLM Home Assistant addon (v2.0+).

## High-Level Goals

- Provide a **self-contained** LLM experience for HAOS users with Hailo AI HAT+ 2 hardware.
- Deliver a **modern interactive chat UI** directly in the addon (no extra containers).
- Remain **fully compatible** as an Ollama-like backend so existing HA conversation integrations and tools continue to work.
- Guarantee **persistence** of models and chat history across reboots using only HAOS-standard `/data` storage.

## Core Components

| Component              | Type          | Location in Container          | Responsibility |
|------------------------|---------------|--------------------------------|----------------|
| `hailo-ollama`         | Binary (C++)  | Installed by `.deb` (`/usr/bin`) | Inference engine. Exposes Ollama-compatible REST API on top of HailoRT. Uses HEF models from the GenAI Model Zoo. |
| Flask Application      | Python (WSGI) | `/opt/hailo_llm/server.py`     | Serves the rich single-page chat UI + acts as a transparent proxy for API compatibility. |
| `run.sh`               | Shell script  | `/opt/hailo_llm/run.sh`        | Entry point. Sets up persistent storage, launches the binary in the background on an internal port, then starts the Python server on the ingress port. |
| Docker Image           | Container     | Built from `Dockerfile`        | aarch64-debian base + Hailo runtime + Python deps + rootfs. |
| Persistent Storage     | Host volume   | `/data` (mapped by HA supervisor) | Models (`/data/models`), chat history (`/data/chats`), addon options. |

## System Diagram (Mermaid)

```mermaid
graph TD
    subgraph Host["Home Assistant Host"]
        HA[Home Assistant Core]
        Supervisor[HA Supervisor]
    end

    subgraph Addon["Hailo LLM Addon Container"]
        subgraph Ingress["Ingress (port 8000)"]
            UI[Modern Chat UI<br/>Tailwind + Vanilla JS]
            Proxy[Flask Proxy Layer]
        end

        Run[run.sh orchestrator]

        subgraph Internal["Internal"]
            Binary["hailo-ollama serve<br/>:11434"]
            FlaskApp[Flask App]
        end

        subgraph Storage["Persistent Data (/data)"]
            Models[(Models<br/>/data/models)]
            Chats[(Chat History<br/>/data/chats)]
            Options[(options.json)]
        end

        Device["/dev/hailo0"]
    end

    HA -->|Ingress panel| UI
    UI -->|API calls| Proxy
    Proxy -->|forward + stream| Binary
    Binary -->|HailoRT| Device
    Run --> Binary
    Run --> FlaskApp
    FlaskApp --> UI
    Binary --> Models
    FlaskApp --> Chats
    Supervisor --> Options
    Supervisor --> Models
    Supervisor --> Chats
```

## Startup Sequence

```mermaid
sequenceDiagram
    participant Supervisor
    participant Run as "run.sh"
    participant Hailo as "hailo-ollama"
    participant Flask
    participant Data as "/data"

    Supervisor->>Run: Start container (CMD)
    Run->>Data: mkdir -p /data/models /data/chats
    Run->>Run: Export OLLAMA_MODELS + symlinks
    Run->>Hailo: Start in background (127.0.0.1:11434)
    Run->>Hailo: Wait for readiness (poll /api/tags)
    Run->>Flask: exec python server.py (port 8000)
    Flask->>Flask: (optional) background auto-download if enabled
    Note over Flask,Hailo: Ready to serve UI + proxy API
```

## Request Flows

### Chat (Streaming)

```mermaid
sequenceDiagram
    participant Browser
    participant Flask
    participant hailo-ollama
    participant NPU

    Browser->>Flask: POST /api/chat {model, messages, stream:true}
    Flask->>hailo-ollama: Forward request (stream)
    hailo-ollama->>NPU: Inference
    NPU-->>hailo-ollama: Tokens
    hailo-ollama-->>Flask: NDJSON stream
    Flask-->>Browser: NDJSON stream (transparent)
    Browser->>Flask: (on completion) POST /api/chats/{id} to persist
```

### Model Download (with Progress)

```mermaid
sequenceDiagram
    participant Browser
    participant Flask
    participant Hailo as "hailo-ollama"
    participant Models as "/data/models"

    Browser->>Flask: POST /api/pull {"model": "qwen2.5:1.5b", stream:true}
    Flask->>Hailo: Forward
    Hailo->>Hailo: Download + convert to HEF (if needed)
    Hailo-->>Flask: Status NDJSON (progress %)
    Flask-->>Browser: Status NDJSON
    Hailo->>Models: Write model files
    Browser->>Flask: Refresh /api/tags
```

## Persistence Layout

```
/data/                     # Persistent volume provided by HA supervisor
├── models/                # OLLAMA_MODELS target. Contains HEF + manifest files
│   └── ...
├── chats/                 # Server-side conversation storage
│   ├── <uuid>.json
│   └── ...
└── options.json           # Addon configuration (read by run.sh + Flask)
```

Chat files are simple JSON:

```json
{
  "id": "...",
  "title": "Conversation about lights",
  "model": "qwen2.5:1.5b",
  "messages": [
    {"role": "user", "content": "...", "ts": 1720000000},
    {"role": "assistant", "content": "...", "ts": 1720000001}
  ],
  "created": 1720000000,
  "updated": 1720000100
}
```

## Key Architectural Decisions

1. **Internal port for the binary + proxy on ingress port**
   - The `hailo-ollama` binary wants to own a port.
   - We need to serve HTML/JS for the UI at the same ingress URL.
   - Solution: binary on `127.0.0.1:11434`, Flask listens on `0.0.0.0:8000` and proxies `/api/*` + `/hailo/*` while serving the UI at `/`.
   - Benefit: users get both a great UI and unchanged API surface.

2. **Server-side chat persistence (instead of only localStorage)**
   - Matches the "models must survive reboot" requirement.
   - Conversations remain available across browsers/devices that can reach the ingress.
   - Simple file-based JSON storage (no extra database dependency).

3. **Self-contained UI**
   - The entire chat interface is a single large HTML string (with Tailwind via CDN + vanilla JS) embedded in `server.py`.
   - No Node build step, no additional static assets to manage in the image.
   - Easy to iterate while keeping the addon image small.

4. **Defensive symlinks for model location**
   - The binary has historically looked in several places (`~/.ollama`, `/usr/share/hailo-ollama`, etc.).
   - We set `OLLAMA_MODELS=/data/models` and create symlinks so future updates to the binary are less likely to break persistence.

5. **Thin proxy instead of re-implementing the server**
   - We rely on the official `hailo-ollama` binary (best performance and model support).
   - The Python layer only adds what is necessary (UI + persistence + auto-download hook).

## Technology Stack Summary

- **Base image**: Home Assistant official aarch64 Debian bookworm
- **Inference**: `hailo-ollama` (C++ / HailoRT 5.3)
- **Web layer**: Flask + requests (proxy + minimal API)
- **Frontend**: Tailwind (CDN) + vanilla JavaScript + Font Awesome (CDN)
- **Process supervisor**: tini (already in base image)
- **Persistence**: Plain files under `/data` (guaranteed by HA supervisor)

## Future Evolution Notes

- The current proxy is intentionally minimal. If the binary's API fidelity improves or more OpenAI-compatible endpoints are needed, the proxy layer can be extended.
- Vision / multimodal support can be added when the Hailo GenAI Zoo ships suitable models and the binary surfaces image inputs.
- A production WSGI server (e.g. gunicorn or waitress) can replace the Flask dev server if load increases.

See [dependencies.md](dependencies.md) for a detailed breakdown of every package and why it exists.
