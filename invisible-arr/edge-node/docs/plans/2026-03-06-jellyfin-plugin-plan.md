# CutDaCord Jellyfin Plugin — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Jellyfin plugin that lets users request movies/shows directly from the Jellyfin web UI, using the existing CutDaCord API.

**Architecture:** C# plugin using the File Transformation pattern (same as Custom Tabs, Media Bar, Home Screen Sections). Plugin registers a startup task that injects `<script>` and `<style>` tags into Jellyfin's `index.html` via the File Transformation plugin. All JS is bundled as embedded resources. JS calls CutDaCord API directly (CORS is open). Auth via Jellyfin SSO auto-link (`/v1/auth/jellyfin-login`).

**Tech Stack:** .NET 9.0 (target `net9.0`), Jellyfin 10.11.6, Newtonsoft.Json, vanilla JavaScript (no framework), CSS3.

**Reference Implementation:** `/tmp/jellyfin-plugin-custom-tabs/` — studied and verified working pattern.

**Key APIs already available (no new backend work needed):**
- `GET /v1/tmdb/search?query=&page=` — TMDB multi-search
- `GET /v1/tmdb/{media_type}/{tmdb_id}` — detail with credits/videos
- `GET /v1/tmdb/tv/{tmdb_id}/seasons` — season list
- `POST /v1/request` — submit request
- `POST /v1/request/batch` — multi-season
- `GET /v1/jobs` — list jobs
- `GET /v1/jobs/{id}/progress` — download progress
- `POST /v1/auth/jellyfin-login` — SSO auto-link

---

## Task 1: Scaffold the C# Plugin Project

**Files:**
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Jellyfin.Plugin.CutDaCord.csproj`
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Plugin.cs`
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Configuration/PluginConfiguration.cs`
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Configuration/config.html`
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Properties/AssemblyInfo.cs`

See Task 1 code blocks in the design doc. Standard Jellyfin plugin scaffold following the Custom Tabs pattern exactly.

**Verify:** `dotnet build -c Release` succeeds with 0 errors.

**Commit:** `feat(jellyfin-plugin): scaffold CutDaCord plugin project`

---

## Task 2: Add File Transformation Registration (Startup Service)

**Files:**
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Model/PatchRequestPayload.cs`
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Helpers/TransformationPatches.cs`
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Services/StartupService.cs`
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Services/StartupServiceHelper.cs`

Pattern copied directly from Custom Tabs — uses `IScheduledTask` with `StartupTrigger`, discovers File Transformation assembly via `AssemblyLoadContext.All`, invokes `RegisterTransformation` with a JObject payload specifying `index.html` as target and `TransformationPatches.IndexHtml` as callback.

The `TransformationPatches.IndexHtml` method reads embedded CSS and JS resources, wraps them in `<style>` and `<script defer>` tags, and regex-inserts them before `</body>`.

**Verify:** `dotnet build -c Release` succeeds.

**Commit:** `feat(jellyfin-plugin): add File Transformation registration and startup service`

---

## Task 3: Create the Injected JavaScript (Core Request Logic)

**Files:**
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Inject/cutdacord.js`

**Security:** All dynamic values (titles, poster paths) MUST be sanitized via `textContent` assignment or URL validation before DOM insertion. No raw string concatenation into DOM. Use `document.createElement` + `textContent`/`src` attribute assignment instead of string-based HTML generation.

The JS handles:
1. **Auto-auth via Jellyfin SSO** — reads `ApiClient.getCurrentUser()` and `ApiClient.accessToken()`, posts to `/v1/auth/jellyfin-login`, stores API key in `localStorage`
2. **Detail page detection** — listens for `hashchange`, `popstate`, and monkey-patched `history.pushState/replaceState`. Matches `#/details?id=` or `#/item?id=` patterns.
3. **Request button injection** — calls `ApiClient.getItem()` to get TMDB ID from `ProviderIds.Tmdb`. Creates button with `document.createElement`, appends to `.mainDetailButtons`.
4. **Request modal** — built with `document.createElement` (no innerHTML with user data). Movie: one-click with download/stream toggle. TV: fetches seasons from `/v1/tmdb/tv/{id}/seasons`, renders checkbox list.
5. **Toast notifications** — success/error/warn toasts for request feedback.

**Key API flow:**
```
User clicks Request → modal opens
  → (TV) fetch /v1/tmdb/tv/{id}/seasons → render season checkboxes
  → User clicks Submit → POST /v1/request or /v1/request/batch
  → Toast: "Requested: {title}" or error message
```

**Commit:** `feat(jellyfin-plugin): add core JavaScript — auth, request modal, detail page button`

---

## Task 4: Create the Injected CSS

**Files:**
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Inject/cutdacord.css`

Dark theme styles matching Jellyfin's aesthetic:
- `.cdc-request-btn` — purple gradient button (indigo-to-violet), hover lift effect
- `.cdc-modal-overlay` / `.cdc-modal` — centered overlay with backdrop blur, dark card
- `.cdc-season-list` — scrollable checkbox list with hover highlight
- `.cdc-toast` — fixed-position notification with slide-up animation
- `.cdc-spinner` — CSS-only loading spinner
- Mobile responsive: stacks poster vertically, full-width modal on small screens

All classes prefixed `cdc-` to avoid collisions with Jellyfin's styles.

**Commit:** `feat(jellyfin-plugin): add CSS styles — modal, buttons, toast, mobile responsive`

---

## Task 5: Build, Deploy, and Test

**Step 1:** Build the plugin DLL

```bash
export PATH="$HOME/.dotnet:$PATH"
cd services/jellyfin-plugin-cutdacord
dotnet build Jellyfin.Plugin.CutDaCord/Jellyfin.Plugin.CutDaCord.csproj -c Release
```

**Step 2:** Deploy to Jellyfin plugins directory

```bash
PLUGIN_DIR="config/jellyfin/plugins/CutDaCord_1.0.0.0"
mkdir -p "$PLUGIN_DIR"
cp Jellyfin.Plugin.CutDaCord/bin/Release/net9.0/Jellyfin.Plugin.CutDaCord.dll "$PLUGIN_DIR/"
cp Jellyfin.Plugin.CutDaCord/bin/Release/net9.0/Jellyfin.Plugin.CutDaCord.pdb "$PLUGIN_DIR/"
# Write meta.json with guid, targetAbi 10.11.6.0, version 1.0.0.0
```

**Step 3:** Restart Jellyfin

```bash
docker compose restart jellyfin
```

**Step 4:** Verify via logs and browser

- Check `docker compose logs jellyfin --tail 50` for `CutDaCord` mentions
- Open browser DevTools → Console → look for `[CutDaCord] Initializing...`
- Navigate to a movie detail page → "Request" button should appear
- Click Request → modal opens → submit → toast appears

**Commit:** `feat(jellyfin-plugin): build and deploy CutDaCord v1.0.0`

---

## Task 6: Add CutDaCord Controller (Plugin Config API)

**Files:**
- Create: `services/jellyfin-plugin-cutdacord/Jellyfin.Plugin.CutDaCord/Controller/CutDaCordController.cs`

Simple ASP.NET controller at `[Route("[controller]")]` exposing `GET /CutDaCord/Config` returning `{ apiBaseUrl }` from plugin config. This lets the JS fetch the API URL dynamically instead of hardcoding.

**Verify:** `curl http://localhost:8096/CutDaCord/Config` returns JSON.

**Commit:** `feat(jellyfin-plugin): add config API endpoint`

---

## Verification Checklist

- [ ] Plugin appears in Jellyfin Admin → Plugins
- [ ] Plugin config page loads with API URL field
- [ ] Console: `[CutDaCord] Initializing...` on page load
- [ ] Console: `[CutDaCord] Authenticated successfully` (SSO auto-link)
- [ ] "Request" button on movie detail pages
- [ ] "Request" button on TV show detail pages
- [ ] Movie modal: Download/Stream toggle, submit works
- [ ] TV modal: season list loads, multi-select works, submit works
- [ ] Toast shows success/error on request
- [ ] Request appears in CutDaCord Activity page
- [ ] Mobile responsive
- [ ] No console errors or XSS vectors

## Dependencies

- **File Transformation plugin** (v2.5.4.0) — already installed at `config/jellyfin/plugins/File Transformation_2.5.4.0/`
- **.NET 9.0 SDK** — installed at `~/.dotnet/` (v9.0.311)
- **CutDaCord API** — all required endpoints already exist, CORS open
