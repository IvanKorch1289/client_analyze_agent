#!/usr/bin/env bash
# =============================================================================
# Tarantool Restore Script
# Restores a Tarantool snapshot from a backup directory.
#
# WARNING: This will STOP the Tarantool container, replace its data, and
# restart it. All current data will be OVERWRITTEN.
#
# Usage:
#   ./scripts/tarantool_restore.sh <backup_timestamp>
#
# Example:
#   ./scripts/tarantool_restore.sh 20260204_120000
#
# The script expects backup files at: ./backups/tarantool/<timestamp>/data/
# =============================================================================

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_timestamp>"
    echo ""
    echo "Available backups:"
    ls -d ./backups/tarantool/20* 2>/dev/null | while read -r d; do
        ts=$(basename "$d")
        stats=""
        if [ -f "$d/stats.txt" ]; then
            stats=" — $(cat "$d/stats.txt")"
        fi
        echo "  ${ts}${stats}"
    done
    exit 1
fi

TIMESTAMP="$1"
BACKUP_DIR="./backups/tarantool/${TIMESTAMP}"
CONTAINER_NAME="${TARANTOOL_CONTAINER:-tarantool-cache}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

# Validate backup exists
if [ ! -d "${BACKUP_DIR}/data" ]; then
    echo "ERROR: Backup not found at ${BACKUP_DIR}/data"
    exit 1
fi

echo "=== Tarantool Restore: ${TIMESTAMP} ==="
echo ""
echo "WARNING: This will STOP Tarantool, REPLACE all data, and restart."
echo "Backup stats: $(cat "${BACKUP_DIR}/stats.txt" 2>/dev/null || echo 'N/A')"
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Step 1: Stop dependent services
echo "[1/5] Stopping app and worker containers..."
docker compose -f "${COMPOSE_FILE}" stop app worker mcp 2>/dev/null || true

# Step 2: Stop Tarantool
echo "[2/5] Stopping Tarantool..."
docker compose -f "${COMPOSE_FILE}" stop tarantool

# Step 3: Replace data
echo "[3/5] Restoring data from backup..."
# Remove old data from volume
docker run --rm -v "$(docker volume ls -q | grep tarantool_data | head -1)":/data alpine sh -c "rm -rf /data/*" 2>/dev/null || {
    echo "WARNING: Could not clean volume directly. Trying alternative method..."
    docker compose -f "${COMPOSE_FILE}" run --rm --no-deps -v "${BACKUP_DIR}/data:/restore:ro" tarantool sh -c "rm -rf /var/lib/tarantool/* && cp -r /restore/* /var/lib/tarantool/" 2>/dev/null
}

# Copy backup data into container volume
docker compose -f "${COMPOSE_FILE}" run --rm --no-deps -v "${BACKUP_DIR}/data:/restore:ro" tarantool sh -c "cp -r /restore/. /var/lib/tarantool/" 2>/dev/null || {
    echo "ERROR: Failed to copy backup data"
    exit 1
}

# Step 4: Restart Tarantool
echo "[4/5] Starting Tarantool..."
docker compose -f "${COMPOSE_FILE}" up -d tarantool

# Wait for health
echo "Waiting for Tarantool to become healthy..."
for i in $(seq 1 30); do
    if docker compose -f "${COMPOSE_FILE}" exec tarantool tarantool -e "print('ok')" 2>/dev/null | grep -q "ok"; then
        echo "Tarantool is healthy."
        break
    fi
    echo "  Waiting... (${i}/30)"
    sleep 2
done

# Step 5: Restart dependent services
echo "[5/5] Starting dependent services..."
docker compose -f "${COMPOSE_FILE}" up -d app worker mcp

# Verify
echo ""
echo "=== Restore Complete ==="
docker compose -f "${COMPOSE_FILE}" exec tarantool tarantool -e "
    local stats = get_space_stats()
    print(string.format('Restored: cache=%d reports=%d threads=%d persistent=%d llm_audit=%d',
        stats.cache, stats.reports, stats.threads, stats.persistent, stats.llm_audit))
" 2>/dev/null || echo "Run 'docker exec tarantool-cache tarantool -e \"print(get_space_stats())\"' to verify"
echo "========================"
