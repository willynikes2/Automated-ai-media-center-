#!/bin/bash
# Jellyfin DVR post-processing script
# Detects and removes commercials from recordings using comskip + comcut
#
# Called by Jellyfin with: postprocess.sh "/path/to/recording.ts"

set -euo pipefail

RECORDING="$1"
LOGFILE="/data/recordings/postprocess.log"
COMSKIP_INI="/etc/comskip/comskip.ini"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOGFILE"
}

log "=== Post-processing started: $RECORDING ==="

if [ ! -f "$RECORDING" ]; then
    log "ERROR: Recording file not found: $RECORDING"
    exit 1
fi

FILESIZE=$(stat -c%s "$RECORDING" 2>/dev/null || echo "0")
log "File size: $((FILESIZE / 1024 / 1024)) MB"

# Step 1: Run comskip to detect commercials
log "Running comskip commercial detection..."
WORKDIR=$(dirname "$RECORDING")
BASENAME=$(basename "$RECORDING")
BASENAME_NOEXT="${BASENAME%.*}"

if comskip --ini="$COMSKIP_INI" --output="$WORKDIR" "$RECORDING" >> "$LOGFILE" 2>&1; then
    log "Comskip detection completed successfully"
else
    COMSKIP_EXIT=$?
    # Exit code 1 means comskip ran but found no commercials — that's OK
    if [ "$COMSKIP_EXIT" -eq 1 ]; then
        log "Comskip found no commercials — skipping comcut"
        # Clean up any partial files
        rm -f "$WORKDIR/$BASENAME_NOEXT.txt" "$WORKDIR/$BASENAME_NOEXT.log" \
              "$WORKDIR/$BASENAME_NOEXT.edl" "$WORKDIR/$BASENAME_NOEXT.vdr"
        log "=== Post-processing complete (no commercials) ==="
        exit 0
    fi
    log "ERROR: Comskip failed with exit code $COMSKIP_EXIT"
    exit 0  # Don't fail the whole recording over comskip errors
fi

# Check if chapter file was generated
CHAPTER_FILE="$WORKDIR/$BASENAME_NOEXT.txt"
if [ ! -f "$CHAPTER_FILE" ]; then
    log "No chapter/EDL file generated — no commercials detected"
    log "=== Post-processing complete (no commercials) ==="
    exit 0
fi

# Step 2: Cut commercials using comcut
log "Running comcut to remove commercials..."
if comcut --comskip-ini="$COMSKIP_INI" "$RECORDING" >> "$LOGFILE" 2>&1; then
    log "Comcut completed successfully"
else
    COMCUT_EXIT=$?
    log "WARNING: Comcut exited with code $COMCUT_EXIT"
    # Don't fail — keep the original recording
fi

# Step 3: Clean up comskip working files
rm -f "$WORKDIR/$BASENAME_NOEXT.txt" \
      "$WORKDIR/$BASENAME_NOEXT.log" \
      "$WORKDIR/$BASENAME_NOEXT.edl" \
      "$WORKDIR/$BASENAME_NOEXT.vdr" \
      "$WORKDIR/$BASENAME_NOEXT.logo.txt"

NEWSIZE=$(stat -c%s "$RECORDING" 2>/dev/null || echo "0")
SAVED=$(( (FILESIZE - NEWSIZE) / 1024 / 1024 ))
log "New file size: $((NEWSIZE / 1024 / 1024)) MB (saved ~${SAVED} MB)"
log "=== Post-processing complete ==="

exit 0
