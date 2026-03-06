# Download Pipeline Redesign: Observer + Fixer Pattern

**Date**: 2026-03-06
**Status**: Approved
**Problem**: 13% job success rate. Worker micro-manages Radarr/Sonarr with tight timeouts, causing failures when Arr apps work at normal pace. Users have no visibility into why downloads fail.

---

## Principles

1. **Arr does the work, worker watches.** The worker never interferes with Radarr/Sonarr doing their job. It observes, reports, and only intervenes when something is actually broken.
2. **No timer-based failures.** Jobs never fail because a clock expired. They only fail when the diagnostic engine confirms an actual unrecoverable problem.
3. **Mom test.** Every user-facing message must be understandable by someone who doesn't know what Radarr is.
4. **Full audit trail.** Every diagnostic finding is logged so patterns can be queried later.

---

## Architecture: Observer + Fixer

### Current (broken)
```
Request -> Worker drives: RESOLVING -> ADDING -> ACQUIRING (120s timeout) -> IMPORTING (300s timeout) -> DONE
           Worker declares failure if ANY timeout expires, even if Arr is still working fine.
```

### New
```
Request -> Add to Arr + Search -> OBSERVE (hands off)
                                      |
                            Arr does its thing naturally
                                      |
                            Worker watches via webhooks + polling fallback
                                      |
                  +-------------------+--------------------+
                  |                   |                    |
            Progressing?         Stuck/errored?      No source?
            -> Report progress   -> Diagnose & fix   -> Try alternatives
            -> Update UI         -> Clear bad grab   -> Relax quality
                                 -> Retry search     -> Report to user
                                 -> Restart if needed
```

### Simplified States

| State | Meaning | What Arr Is Doing |
|-------|---------|-------------------|
| CREATED | Job queued | Nothing yet |
| SEARCHING | Worker added to Arr, search triggered | Arr querying indexers |
| DOWNLOADING | Arr grabbed a release, download in progress | rdt-client/qBit downloading |
| IMPORTING | Download complete, Arr organizing file | Arr copying/hardlinking to user folder |
| DONE | File in user library, verified | Complete |
| MONITORED | Content not released yet | Arr monitoring, worker checks periodically |
| INVESTIGATING | Something went wrong, worker diagnosing | Worker running diagnostic engine |
| UNAVAILABLE | Exhausted all options, unrecoverable | Nothing — user informed |

**Removed states**: RESOLVING, ADDING, ACQUIRING, VERIFYING (these were internal worker phases that don't mean anything to users)

---

## Webhook Integration

### Radarr/Sonarr Webhook Configuration

Register webhooks in Arr settings pointing to:
```
POST /v1/webhooks/radarr
POST /v1/webhooks/sonarr
```

### Events and Actions

| Webhook Event | Worker Action |
|--------------|---------------|
| `on_grab` | SEARCHING -> DOWNLOADING; record release name, indexer, quality |
| `on_download` / `on_import` | DOWNLOADING -> IMPORTING -> verify user folder -> DONE |
| `on_download_failure` | Diagnose; blacklist release; re-search |
| `on_health_issue` | Log; restart container if unresponsive |
| `on_movie_file_delete` / `on_episode_file_delete` | Update storage tracking |

### Polling Fallback (Safety Net)

- Runs every **60s** (was 15s)
- Only checks jobs that haven't received a webhook in 10+ minutes
- Queries Arr directly to catch missed events
- NOT the primary driver — just catches edge cases

---

## Diagnostic Engine

### How It Works

When the worker detects a problem (no grab after 5 min, stalled download, import error), it queries Arr's own data to determine the actual root cause.

**Data sources for diagnosis:**
- `GET /api/v3/history` — what did Arr try? What was rejected and why?
- `GET /api/v3/queue` — current download status, warnings, errors
- `GET /api/v3/blocklist` — what's been blacklisted
- `GET /api/v3/health` — Arr system health
- Indexer stats from Prowlarr — are indexers responding?

### Diagnostic Categories

| Category | Detection | Auto-Fix | User Message |
|----------|-----------|----------|-------------|
| `no_releases` | Arr history shows search with 0 results | MONITORED; check daily | "No downloads available yet — we'll keep checking" |
| `quality_rejected` | History shows releases found but all rejected by quality profile | Re-search with relaxed quality cutoff | "Available versions don't meet quality standards — trying with relaxed settings" |
| `indexer_error` | History shows indexer timeouts/errors | Retry search after 5 min | "Search providers having issues — retrying shortly" |
| `download_stalled` | Queue item at 0% for 10+ min, or no progress for 10+ min | Blacklist release, re-search | "Download stalled — switching to another source" |
| `import_blocked` | Queue item status is importBlocked/importFailed | Check paths, refresh Arr, clear block | "File downloaded but can't be organized — investigating" |
| `arr_unresponsive` | Arr API returns connection errors | Restart container, re-enqueue | "Download service restarting — your request will resume" |
| `disk_full` | ENOSPC or Arr health warning | Notify user, don't retry | "Storage full — please free up space or upgrade" |
| `content_not_released` | Movie status announced/inCinemas, or episode airDate in future | MONITORED with expected date | "Not released yet — we'll grab it automatically on {date}" |

### Diagnostic Storage

```sql
CREATE TABLE job_diagnostics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    diagnosed_at TIMESTAMP NOT NULL DEFAULT now(),
    category VARCHAR(50) NOT NULL,      -- 'no_releases', 'quality_rejected', etc.
    details_json JSON,                   -- raw Arr response data, indexer names, rejection reasons
    auto_fix_action VARCHAR(200),        -- what the worker did about it
    resolved BOOLEAN DEFAULT FALSE,      -- did the fix work?
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_diagnostics_job_id ON job_diagnostics(job_id);
CREATE INDEX idx_job_diagnostics_category ON job_diagnostics(category);
```

---

## Timeout Philosophy

### Old: Timer-Based Failure
```
Search triggered -> wait 120s -> no grab? -> FAILED
Download started -> wait 300s -> no import? -> FAILED
```

### New: Problem-Based Intervention
```
Search triggered -> webhook or 5 min poll -> no activity?
    -> Query Arr history for rejection reasons
    -> Diagnose actual problem
    -> Apply fix or escalate to INVESTIGATING
    -> Only UNAVAILABLE after exhausting all auto-fixes
```

**Intervention thresholds** (not timeouts — the job doesn't fail at these, the worker investigates):
- No grab after 5 min → run diagnostics on Arr history
- Download at 0% for 10 min → check if stalled
- No import after download complete + 10 min → check Arr queue status
- INVESTIGATING for 2+ hours with no resolution → UNAVAILABLE with full explanation

**Max auto-fix attempts per job**: 5 (same as current retry count, but now each attempt includes a real diagnosis)

---

## Frontend Changes

### User-Facing States

| State | Display | Visual |
|-------|---------|--------|
| SEARCHING | "Looking for the best version..." | Magnifying glass + spinner |
| DOWNLOADING | "Downloading — 45% (12 min left)" | Progress bar with percentage |
| IMPORTING | "Organizing into your library..." | Folder + spinner |
| DONE | "Ready to watch!" | Green checkmark |
| MONITORED | "Not released yet — we'll grab it on {date}" | Clock with date |
| INVESTIGATING | "Having trouble — working on it" | Wrench + spinner |
| UNAVAILABLE | "No downloads available right now — checking daily" | Info icon |

### No More FAILED State in UI

Internal failures trigger the diagnostic engine. Users see either INVESTIGATING (worker is fixing it) or UNAVAILABLE (nothing more can be done, with a plain-English explanation).

FAILED still exists in the database for internal tracking, but the frontend maps it:
- FAILED + has pending auto-fix → show as INVESTIGATING
- FAILED + exhausted retries → show as UNAVAILABLE + reason

### Job Timeline (Activity Page)

Each job shows a collapsible timeline:
```
  Searched for "The Matrix"
  Found: The.Matrix.1999.2160p.UHD.BluRay.x265 (indexer: NZBgeek)
  Downloading — completed in 2m 34s
  Organized into your library
  Ready to watch!
```

Or for problems:
```
  Searched for "Whistle"
  No sources found matching quality settings
  Retrying with relaxed quality...
  Found: Whistle.2026.1080p.WEB-DL.x264 (indexer: TorrentLeech)
  Downloading — completed in 45s
  Ready to watch!
```

### Detail Expand (Admin View)

Tapping a timeline entry shows diagnostic details:
- Indexer responses, rejection reasons, quality scores
- Which releases were tried and why they failed
- Arr API response data
- Time spent in each phase

---

## Cleanup: Dead Code Removal

- Remove all streaming/Zurg code paths from worker (already disabled, causing ghost failures)
- Remove `ARR_GRAB_TIMEOUT_STREAM` / `ARR_GRAB_TIMEOUT_DOWNLOAD` constants
- Remove `_wait_for_grab` tight polling loop
- Remove old download monitor 15s poll loop (replaced by webhook + 60s fallback)

---

## Migration Plan

### Database
1. Add `job_diagnostics` table
2. Add new states to job state enum: `SEARCHING`, `DOWNLOADING`, `INVESTIGATING`, `UNAVAILABLE`
3. Migrate existing job states: `RESOLVING`/`ADDING` -> `SEARCHING`, `ACQUIRING` -> `DOWNLOADING`

### Arr Configuration
1. Register webhook URLs in Radarr settings
2. Register webhook URLs in Sonarr settings
3. Webhook secret token for authentication

### Worker
1. Add webhook receiver endpoints to agent-api
2. Rewrite worker pipeline: remove tight timeouts, add diagnostic engine
3. Replace download monitor with webhook handler + 60s fallback poll
4. Add diagnostic storage layer

### Frontend
1. Map new states to UI components
2. Add job timeline component
3. Replace error messages with mom-friendly text
4. Add detail-expand for admin diagnostics

---

## Success Criteria

1. **No job fails due to a timeout alone** — only due to diagnosed, unrecoverable problems
2. **Every failure has a diagnostic record** with category, details, and auto-fix attempted
3. **Users never see technical error messages** — only plain-English status
4. **Success rate > 90%** for content that actually exists and has releases available
5. **Mom test passes** — non-technical user can request content, understand status, and never need to log into Radarr/Sonarr
