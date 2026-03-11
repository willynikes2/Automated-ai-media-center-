#!/bin/bash
# Ensure rdt-client auth stays disabled after restarts.
# rdt-client stores auth in SQLite — this script patches it on container start.
# Mount as custom-init script or run after container starts.

DB="/data/db/rdtclient.db"

if [ ! -f "$DB" ]; then
    echo "[fix-rdtclient-auth] DB not found at $DB — skipping"
    exit 0
fi

# Check if sqlite3 is available
if command -v sqlite3 &>/dev/null; then
    sqlite3 "$DB" "UPDATE Settings SET Value = 'None' WHERE SettingId = 'General:AuthenticationType' AND Value != 'None';"
    CHANGED=$?
    if [ $CHANGED -eq 0 ]; then
        echo "[fix-rdtclient-auth] Auth disabled in rdt-client DB"
    fi
else
    # Fallback: use python if available
    python3 -c "
import sqlite3, sys
conn = sqlite3.connect('$DB')
c = conn.cursor()
c.execute(\"SELECT Value FROM Settings WHERE SettingId = 'General:AuthenticationType'\")
row = c.fetchone()
if row and row[0] != 'None':
    c.execute(\"UPDATE Settings SET Value = 'None' WHERE SettingId = 'General:AuthenticationType'\")
    conn.commit()
    print('[fix-rdtclient-auth] Auth disabled in rdt-client DB')
else:
    print('[fix-rdtclient-auth] Auth already disabled')
conn.close()
" 2>/dev/null || echo "[fix-rdtclient-auth] No sqlite3 or python3 available — cannot patch"
fi
