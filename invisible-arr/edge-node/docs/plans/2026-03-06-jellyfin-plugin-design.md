# CutDaCord Jellyfin Plugin — Design Doc

*2026-03-06*

## Problem

Users must leave Jellyfin to request content via the CutDaCord web app. We want an integrated "Request" experience directly inside the Jellyfin player UI.

## Approach: Client-Side JS Injection Plugin

A C# Jellyfin plugin that injects JavaScript and CSS into the web UI. JS calls the CutDaCord API directly (CORS is open, no CSP restrictions). No server-side proxy required.

## User-Facing Features

### 1. Request Button on Detail Pages
- Mutation observer detects navigation to movie/show detail pages
- Reads TMDB ID from item metadata via `window.ApiClient.getItem()`
- Adds a "Request" button next to Play/Trailer buttons
- TV shows: season/episode selector dropdown
- Shows existing request status if already requested

### 2. CutDaCord Navigation Tab
- Injected into Jellyfin's sidebar/header navigation
- Full search interface: search bar → TMDB results grid with poster cards
- Click result → request modal (quality, season selection, download vs stream)
- Active requests panel showing job status and download progress

### 3. Status Notifications
- Floating toast/badge showing active download count and progress
- Badge count on the CutDaCord nav tab

## Architecture

```
Browser (Jellyfin Web UI)
  └─ cutdacord.js (injected by C# plugin)
       ├─ window.ApiClient → Jellyfin API (get item metadata, TMDB IDs)
       └─ fetch() → CutDaCord API at /api/v1/* (requests, jobs, search)
            └─ X-Api-Key header for auth
```

### Authentication Flow
1. First visit: plugin detects no stored API key
2. Shows setup modal: user enters CutDaCord credentials OR auto-links via Jellyfin SSO (`/v1/auth/jellyfin-login`)
3. API key stored in `localStorage` (namespaced: `cutdacord_api_key`)
4. All subsequent API calls include `X-Api-Key` header

### Plugin File Structure
```
jellyfin-plugin-cutdacord/
├── Jellyfin.Plugin.CutDaCord/
│   ├── Plugin.cs                      # Plugin metadata and entry
│   ├── Configuration/
│   │   └── PluginConfiguration.cs     # API base URL config
│   ├── EntryPoints/
│   │   └── ClientScriptEntryPoint.cs  # Injects <script>/<link> into HTML head
│   └── CutDaCord.csproj
├── web/
│   ├── cutdacord.js                   # Main script (vanilla JS, no framework)
│   ├── cutdacord.css                  # Dark theme styles matching Jellyfin
│   └── components/
│       ├── request-button.js          # Detail page button + season picker
│       ├── request-modal.js           # Request confirmation dialog
│       ├── search-tab.js              # Full search/browse UI
│       └── status-toast.js            # Download progress notifications
└── build/
```

## API Dependencies

### Existing Endpoints Used
| Endpoint | Purpose |
|----------|---------|
| `POST /v1/auth/jellyfin-login` | SSO auto-link (jellyfin_user_id → api_key) |
| `POST /v1/request` | Submit content request |
| `POST /v1/request/batch` | Multi-season TV requests |
| `GET /v1/jobs` | List user's active/completed requests |
| `GET /v1/jobs/{id}/progress` | Download progress polling |
| `POST /v1/jobs/{id}/cancel` | Cancel a request |

### New Endpoint Needed
| Endpoint | Purpose |
|----------|---------|
| `GET /v1/search/tmdb` | TMDB movie/TV search for discovery tab |

The frontend currently handles TMDB search. We need a server-side endpoint so the plugin doesn't need a separate TMDB API key. Params: `query`, `media_type`, `page`. Returns poster, title, year, overview, tmdb_id.

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| API calls | Direct fetch to CutDaCord API | CORS open, simplest path, no proxy overhead |
| Auth storage | localStorage | Matches existing frontend pattern, per-browser |
| UI framework | Vanilla JS | No build step, small bundle, matches Jellyfin plugin conventions |
| TMDB search | Server-side proxy endpoint | Keeps API key server-side, single source of truth |
| Style | CSS custom properties | Inherits Jellyfin's theme variables for dark mode compat |

## Scope & Phases

### Phase 1 (MVP)
- C# plugin shell with script injection
- Request button on movie/show detail pages
- Simple request modal (one-click for movies, season picker for TV)
- localStorage auth with manual API key entry

### Phase 2
- CutDaCord search/browse tab in navigation
- TMDB search endpoint in agent-api
- Active request status badges

### Phase 3
- Jellyfin SSO auto-link (zero-config for users)
- Download progress toasts
- "My Requests" history view

## Risk: Jellyfin Updates Breaking DOM Selectors
Jellyfin's web UI is a SPA with no stable plugin API for client-side JS. DOM selectors may break across versions. Mitigation:
- Use broad selectors (data attributes, aria roles) over fragile class names
- Mutation observers with fallback retry logic
- Version-check on plugin load, warn if untested Jellyfin version
