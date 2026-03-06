# Task Tracker

> Persistent task list across sessions. Claude reads this at session start.

## In Progress
- [ ] **TRIAGE: Radarr → rdt-client → Real-Debrid pipeline broken** — Radarr grabs releases but they never reach RD. rdt-client appears to receive grabs but doesn't add torrents. See `memory/current-work.md` for full triage steps.

## Up Next
- [ ] Test stream mode end-to-end (blocked on RD pipeline fix)
- [ ] Test download mode end-to-end
- [ ] Design user-editable quality profiles with Trash Guides defaults

## Completed
- [x] Fix stale rclone VFS ghost detection in _pick_zurg_source (2026-03-05)
- [x] Fix agent-qc Jellyfin auth token (2026-03-05)
- [x] Fix stream mode when file already exists locally (2026-03-05)
- [x] Clean all test data for fresh testing (2026-03-05)
- [x] Add Zurg + rclone services to docker-compose + config files (2026-03-05)
- [x] Fix QC race condition: transition to VERIFYING before enqueuing QC (2026-03-05)
- [x] Fix worker logging: check actual job state, not just non-exception return (2026-03-05)
- [x] Fix frontend activity page: staleTime=0 for job queries (2026-03-05)
- [x] Commit c38de42 — all Zurg infra + bug fixes (2026-03-05)
- [x] Set up checkpoint/memory system (2026-03-04)
- [x] Audit search and download pipeline — found 6 bugs, all fixed (2026-03-04)
- [x] Audit frontend links, routes, and build — found 5 bugs, fixed key ones (2026-03-04)
- [x] Review Codex changes for correctness — validated, issues fixed (2026-03-04)
- [x] Root cause analysis: Sinners (no Zurg service) + Shelter (frontend polling bug) (2026-03-04)
- [x] Layer 1 cleanup: test data, .bak files, stale Arr entries, DB/Redis (2026-03-04)
- [x] Push all changes to GitHub: commit 4baef34 (2026-03-04)
