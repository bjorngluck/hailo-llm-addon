#!/bin/bash
# Combined cleanup script for stuck Hailo LLM addon installs in Home Assistant
# Run this in the Terminal & SSH addon or via SSH.

echo "=== Cleaning up Hailo LLM addon state ==="

# 1. Remove old git clone
echo "Removing git clone..."
rm -rf /data/apps/git/7d290ede 2>/dev/null || true
rm -rf /data/apps/git/*hailo* 2>/dev/null || true

# 2. Uninstall any variants
echo "Uninstalling addon variants..."
ha addon uninstall hailo_llm || true
ha addon uninstall local_hailo_llm || true
ha addon uninstall 7d290ede_hailo_llm || true

# 3. Clean docker images
echo "Cleaning docker images..."
docker rmi -f $(docker images | grep -E 'hailo_llm|7d290ede|local_hailo' | awk '{print $3}') 2>/dev/null || true
docker image prune -f

# 4. Restart supervisor
echo "Restarting supervisor..."
ha supervisor restart

echo ""
echo "Wait 60 seconds, then run:"
echo "  ha addon build --no-cache local_hailo_llm"
echo "  ha addon install local_hailo_llm"
echo ""
echo "=== Cleanup complete ==="
