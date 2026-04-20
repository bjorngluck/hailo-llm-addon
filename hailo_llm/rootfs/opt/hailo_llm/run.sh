#!/bin/bash
set -e

echo "Starting Hailo LLM..."

export OLLAMA_KEEP_ALIVE="300m"

exec hailo-ollama serve --host 0.0.0.0 --port 8000