# Task Tracker

> Persistent task list across sessions. Claude reads this at session start.

## In Progress


## Up Next
- [ ] Test stream mode end-to-end (Sinners-like request via stream)
- [ ] Test download mode end-to-end (Shelter-like request, verify frontend reflects completion)
- [ ] Design user-editable quality profiles with Trash Guides defaults

## Completed
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
