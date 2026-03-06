# CutDaCord UI/UX Review — Gemini 2.5 Pro

*Generated 2026-03-06 via Daniel multi-agent orchestrator*

## 1. Top 5 UI Improvements for a Premium Feel

1. **Dynamic Hero Banner** — Replace static grid on Discover with full-width hero for trending title. Backdrop image + title overlay + synopsis + "Watch Trailer" / "Request" CTA. Subtle parallax scroll.

2. **"Continue Watching" Shelf** — Most important for retention. First or second carousel on Discover/Library. Cards with progress bar overlaid on poster.

3. **Enhanced Media Cards** — On hover: subtle zoom + overlay buttons (Watchlist, Play Trailer). TV show season count badge. Makes UI feel alive.

4. **Skeleton Loading Screens** — Replace spinners with layout-mimicking placeholders. Grey boxes shaped like poster cards, text lines, buttons. Feels faster.

5. **Integrated Playback Experience** — Wrap Jellyfin iframe in seamless dark-themed playback page/modal. App branding + custom "next episode" / "back to library" controls outside iframe.

## 2. Mobile UX Recommendations

1. **Thumb-Friendly Action Bar** — Sticky floating bar at bottom of media detail pages with Play, Request, Watchlist actions.

2. **Gesture-Based Navigation** — Swipe left/right on carousels. More natural than arrow buttons on mobile.

3. **Dedicated Casting Button** — Chromecast/AirPlay in header and playback screen. Non-negotiable for streaming app.

4. **Mobile-First Search** — Tap search icon -> instant keyboard focus on large input, dynamic results as user types.

## 3. Missing UX Patterns & Features

1. **User Profiles** — Separate watch histories/libraries/recommendations per family member. Critical for Family/Power tiers. Profile switcher on login + avatar dropdown in header.

2. **Watchlist ("My List")** — Bookmark content without requesting. "Add to Watchlist" button on every card/detail page. New Watchlist nav page.

3. **Trailer Integration** — "Watch Trailer" button on detail pages, opens modal. Pull trailer URL from TMDB API.

4. **Content Collections** — Group franchises (MCU, LOTR, etc.) using TMDB `belongs_to_collection` field. Special carousels or Collections page.

## 4. Design System Recommendations

- **Color**: Dark theme + single vibrant accent (electric blue or warm orange). Use exclusively for primary CTAs, focused elements, progress bars.
- **Typography**: Modern sans-serif (Inter or Poppins). Strict typographic scale: H1 page titles, H2 carousel titles, Body descriptions.
- **Spacing**: 8px grid system. Multiples of 8 (8, 16, 24, 32) for all padding/margins/gaps.
- **Animation**: Subtle, fast. Fades for page transitions. Scale/fade for micro-interactions. No slow/complex animations.

## 5. Specific Component Ideas

- **"Top 10" Carousel** — Stylized numbers next to posters. "Top 10 Movies Today" / "Top 10 Shows This Week".
- **Personalized Recommendation Rows** — "Because you watched [Title]", "New Episodes This Week" based on watch history.
- **"Coming Soon" / Notifications** — Section for anticipated unreleased content + "Notify Me" button.

## Priority Matrix (Claude's Assessment)

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P0 | Hero Banner on Discover | Medium | Very High |
| P0 | Skeleton Loading | Low | High |
| P0 | Enhanced Media Cards (hover) | Low | High |
| P1 | Continue Watching shelf | Medium | Very High |
| P1 | Watchlist / My List | Medium | High |
| P1 | Trailer Integration | Low | Medium |
| P1 | Mobile sticky action bar | Low | High |
| P2 | Top 10 Carousel | Low | Medium |
| P2 | Content Collections | Medium | Medium |
| P2 | Integrated Playback wrapper | High | High |
| P3 | User Profiles | Very High | High |
| P3 | Casting support | Very High | Medium |
