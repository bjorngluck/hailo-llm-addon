#!/bin/bash
# Combined cleanup script for stuck Hailo LLM addon installs in Home Assistant
# Run this in the Terminal & SSH addon or via SSH.

echo "=== Cleaning up Hailo LLM addon state ==="

# 1. Remove old git clones (HA caches custom repo clones here)
echo "Removing git clones..."
rm -rf /data/apps/git/7d290ede 2>/dev/null || true
rm -rf /data/apps/git/*hailo* /data/apps/git/*llm* 2>/dev/null || true
rm -rf /data/addons/git/*hailo* /data/addons/git/*llm* 2>/dev/null || true

# Try to find and remove any lingering clone of this specific repo
find /data -path '*/.git/config' -exec grep -l 'bjorngluck/hailo-llm-addon' {} + 2>/dev/null | while read -r cfg; do
  dir=$(dirname "$(dirname "$cfg")")
  echo "Removing stale clone: $dir"
  rm -rf "$dir" 2>/dev/null || true
done

# 2. Uninstall any variants (use both 'app' and 'addon' as CLI varies)
echo "Uninstalling addon variants..."
ha app uninstall hailo_llm || true
ha app uninstall local_hailo_llm || true
ha app uninstall 7d290ede_hailo_llm || true
ha addon uninstall hailo_llm || true
ha addon uninstall local_hailo_llm || true
ha addon uninstall 7d290ede_hailo_llm || true

# 3. Clean docker images
echo "Cleaning docker images..."
docker rmi -f $(docker images | grep -E 'hailo_llm|7d290ede|local_hailo' | awk '{print $3}') 2>/dev/null || true
docker image prune -f

# 4. Force reload/repair of supervisor and store to clear cache
echo "Reloading supervisor and store..."
ha supervisor reload || true
ha supervisor repair || true
ha store reload || true

# 5. Restart supervisor
echo "Restarting supervisor..."
ha supervisor restart

echo ""
echo "Wait 60 seconds, then:"
echo "  ha app list | grep -i hailo"
echo "  ha addon list | grep -i hailo"
echo ""
echo "Remove + re-add the custom repo in HA UI if still not seeing 2.0.42+"
echo "Then hard refresh browser (Ctrl+Shift+R)."
echo ""
echo "If addon appears but no Update:"
echo "  ha app update hailo_llm || true"
echo "  ha addon update hailo_llm || true"
echo ""
echo "Or use Rebuild from the addon page UI."
echo ""
echo "For clean install:"
echo "  # ha app build --no-cache local_hailo_llm || true"
echo "  # ha app install local_hailo_llm"
echo ""
echo "=== Cleanup complete ==="
