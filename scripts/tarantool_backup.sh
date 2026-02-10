#!/usr/bin/env bash
# =============================================================================
# Tarantool Backup Script
# Creates a snapshot of all Tarantool spaces (cache, reports, threads,
# persistent, llm_audit) and copies it to a timestamped backup directory.
#
# Usage:
#   ./scripts/tarantool_backup.sh [backup_dir]
#
# Defaults:
#   backup_dir = ./backups/tarantool
#
# Can be scheduled via cron:
#   0 */4 * * * /opt/counterparty-analyzer/scripts/tarantool_backup.sh
# =============================================================================

set -euo pipefail

BACKUP_DIR="${1:-./backups/tarantool}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SNAPSHOT_DIR="${BACKUP_DIR}/${TIMESTAMP}"
CONTAINER_NAME="${TARANTOOL_CONTAINER:-tarantool-cache}"
TARANTOOL_DATA_VOLUME="tarantool_data"
MAX_BACKUPS="${MAX_TARANTOOL_BACKUPS:-24}"  # Keep last 24 backups (4 days at 4h interval)

echo "=== Tarantool Backup: ${TIMESTAMP} ==="
echo "Backup dir: ${SNAPSHOT_DIR}"

# Create backup directory
mkdir -p "${SNAPSHOT_DIR}"

# Step 1: Trigger snapshot inside Tarantool
echo "[1/4] Triggering Tarantool snapshot..."
docker exec "${CONTAINER_NAME}" tarantool -e "box.snapshot()" 2>/dev/null || {
    echo "WARNING: box.snapshot() failed (may already be running). Continuing with existing files."
}

# Step 2: Copy snapshot files from container
echo "[2/4] Copying snapshot files..."
docker cp "${CONTAINER_NAME}:/var/lib/tarantool/" "${SNAPSHOT_DIR}/data" 2>/dev/null || {
    echo "ERROR: Failed to copy data from container"
    exit 1
}

# Step 3: Save space stats for verification
echo "[3/4] Saving space statistics..."
docker exec "${CONTAINER_NAME}" tarantool -e "
    local stats = get_space_stats()
    print(string.format('cache=%d reports=%d threads=%d persistent=%d llm_audit=%d',
        stats.cache, stats.reports, stats.threads, stats.persistent, stats.llm_audit))
" 2>/dev/null > "${SNAPSHOT_DIR}/stats.txt" || echo "WARNING: Could not save stats"

# Save init.lua alongside backup for schema reference
cp app/storage/init.lua "${SNAPSHOT_DIR}/init.lua" 2>/dev/null || true

# Step 4: Rotate old backups
echo "[4/4] Rotating old backups (keeping last ${MAX_BACKUPS})..."
BACKUP_COUNT=$(ls -d "${BACKUP_DIR}"/20* 2>/dev/null | wc -l)
if [ "${BACKUP_COUNT}" -gt "${MAX_BACKUPS}" ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
    ls -d "${BACKUP_DIR}"/20* 2>/dev/null | head -n "${REMOVE_COUNT}" | while read -r old_backup; do
        echo "  Removing old backup: $(basename "${old_backup}")"
        rm -rf "${old_backup}"
    done
fi

# Summary
BACKUP_SIZE=$(du -sh "${SNAPSHOT_DIR}" 2>/dev/null | cut -f1)
echo ""
echo "=== Backup Complete ==="
echo "Location: ${SNAPSHOT_DIR}"
echo "Size: ${BACKUP_SIZE}"
if [ -f "${SNAPSHOT_DIR}/stats.txt" ]; then
    echo "Stats: $(cat "${SNAPSHOT_DIR}/stats.txt")"
fi
echo "========================"
