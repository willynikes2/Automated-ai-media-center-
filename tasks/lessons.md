# Lessons Learned

> Updated when corrections happen. Claude reviews this at session start.

## Session Management
- **Always checkpoint before ending a session.** User expects continuity across sessions.
- **Read `tasks/todo.md` and `memory/current-work.md` at session start** to restore context.

## Stream Mode
- **rclone VFS cache can serve ghost entries.** Files that exist in the cache listing but are gone from Real-Debrid will return 404. Always `stat()` a matched file before trusting it.
- **"hasFile" in Radarr/Sonarr means LOCAL file, not Zurg file.** In stream mode, skip Zurg pointer when Arr already has a local copy — the movie is already available.
- **Radarr grab ≠ Real-Debrid availability.** Just because Radarr grabbed a release doesn't mean rdt-client successfully added it to RD. Verify the full chain.

## Jellyfin
- **Jellyfin requires auth even on internal Docker network.** Always pass `X-Emby-Token` header for API calls including `/Library/Refresh`.

## QC
- **State transition must happen BEFORE enqueuing dependent work.** The QC service checks `state == VERIFYING` and skips if still `IMPORTING`. Transition first, enqueue second.
