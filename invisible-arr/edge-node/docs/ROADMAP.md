# CutDaCord Roadmap

## Real-Time Toast Notifications

Status: PLANNED

Push real-time notifications to users when job state changes (especially failures).
Requires WebSocket or SSE infrastructure from agent-api to frontend.

### Use Cases
- Job fails: toast with friendly error (e.g. "Scream 7: Not yet released")
- Job completes: toast with "Movie ready to watch"
- Download progress: optional progress bar in header

### Implementation Notes
- Add WebSocket endpoint to agent-api (FastAPI WebSocket support)
- Worker publishes state changes to Redis pub/sub
- API subscribes and pushes to connected clients
- Frontend: connect on mount, show toast on message

## Streaming Mode (Zurg/STRM)

Status: DISABLED

See `docs/ROADMAP_STREAMING.md` for details.
