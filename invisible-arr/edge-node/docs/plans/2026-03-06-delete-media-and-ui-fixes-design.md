# Delete Media + UI Fixes Design

Date: 2026-03-06

## 1. Delete Media Feature

### Delete Chain (always, full cleanup)
1. Delete file(s) from disk, remove empty parent folders
2. Remove from Radarr (delete_movie) or Sonarr (delete_series/episode files)
3. Refresh Jellyfin library so stale items disappear
4. Update user.storage_used_gb (subtract freed space)
5. Mark related job(s) as DELETED (new JobState)

### API

```
DELETE /v1/library/item
Body: {
  "file_path": string,              # absolute path to file or folder
  "media_type": "movie" | "tv",
  "delete_scope": "file" | "season" | "series"
}
Response: { "freed_bytes": int }
```

Security: validate path is under user's media directory before any deletion.

### TV Delete Granularity
- **file**: delete single episode file
- **season**: delete season folder and all episodes in it
- **series**: delete entire series folder, all seasons, remove from Sonarr

### Frontend - Library Card Delete
- Trash icon overlay on hover (top-right corner of MediaCard)
- Click opens confirmation modal with title + size
- For TV cards: modal offers scope choice (episode / season / series)
- On success: invalidate library + storage-info query caches

### Frontend - Detail Page Delete
- Rewire existing delete modal in LibraryItemPage.tsx to use new backend endpoint
- Same confirmation flow, shows file details before delete

### New Job State
- Add DELETED to JobState enum in shared/models.py
- Jobs whose media is deleted transition to DELETED
- Activity page: deleted items shown grayed out or filtered via Deleted tab

## 2. User Avatar Dropdown

Current state: avatar div in TopBar.tsx is non-interactive.

### Implementation
- Click avatar opens dropdown menu with:
  - User name + email
  - Tier badge
  - Settings link
  - Sign Out button
- Close on click outside or Escape key
- Use existing useLogout() hook for sign out

## 3. Bug Report Button Overlap Fix

Current: fixed at bottom-6 right-6, overlaps MobileNav settings on small screens.

Fix: add responsive positioning — bottom-20 right-6 on mobile (md:bottom-6) to sit above MobileNav.

## Files to Modify

### Backend
- services/agent-api/routers/library.py — add DELETE endpoint
- services/shared/models.py — add DELETED to JobState
- services/shared/jellyfin_client.py — add refresh after delete
- services/shared/sonarr_client.py — add delete_episode_file method

### Frontend
- src/components/layout/TopBar.tsx — avatar dropdown with logout
- src/components/ui/BugReportButton.tsx — responsive positioning
- src/pages/LibraryPage.tsx — trash icon on MediaCard
- src/pages/LibraryItemPage.tsx — rewire delete to new endpoint
- src/api/media.ts — add deleteMediaItem function
- src/hooks/useMedia.ts — add useDeleteMediaItem hook
- src/pages/ActivityPage.tsx — handle DELETED state display
