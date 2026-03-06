# Universal Agent Instructions

> Portable instructions for any AI coding assistant (Claude, Codex, Gemini, etc.)
> Exported from Claude Code setup on 2026-03-05.
> Source: Shawn's ~/.claude/ config, plugins, and MCP servers.

---

## Table of Contents

1. [Operating Contract](#operating-contract)
2. [Project Context](#project-context)
3. [Workflow Skills](#workflow-skills)
4. [MCP Servers & External Tools](#mcp-servers--external-tools)
5. [Usage Notes for Gemini](#usage-notes-for-gemini)

---

## Operating Contract

### Planning Discipline
- Enter plan mode for ANY non-trivial task (3+ steps, architectural decisions, refactors).
- If something deviates from plan, STOP and re-plan before proceeding.
- Write clear, structured specs before building.

### Subagent / Parallel Strategy
- Offload research, exploration, and parallel analysis to subagents/threads when available.
- One focused objective per subagent.
- Keep main context clean.

### Continuous Self-Improvement
- After ANY user correction, update `tasks/lessons.md` with mistake pattern and prevention rule.
- Review lessons at the start of each session.

### Verification Before Completion
- Never mark work complete without proof.
- Run relevant tests, check logs, validate expected behavior.
- Ask: "Would a staff engineer approve this change?"

### Elegance (Balanced)
- Pause and ask: "Is there a more elegant solution?"
- Do NOT over-engineer simple fixes.
- Prefer simplicity, clarity, minimal surface area.

### Autonomous Bug Resolution
- Investigate logs, identify failing tests, fix root cause.
- Don't ask for step-by-step guidance on bugs.

### Task Management
1. Write plans to `tasks/todo.md` with checkable items.
2. Confirm plan before implementation.
3. Mark progress as tasks complete.
4. Add a review section after completion.

### Core Principles
- **Simplicity First** - Minimal necessary change.
- **No Laziness** - Fix root causes, not symptoms.
- **Minimal Impact** - Don't introduce new instability.
- **Proof Over Assumption** - Demonstrate correctness.
- **Clarity Over Cleverness** - Prefer maintainable code.

---

## Project Context

### CutDaCord.app - Automated Media Center

**Vision:** AI-orchestrated automated media center wrapping the *Arr ecosystem. Users interact only with Seerr (requests) and Jellyfin (playback). Everything else is automated.

**Architecture:**
- Edge Node (Docker Compose on VPS): Traefik, Jellyfin, Frontend PWA, Seerr
- Hidden: Sonarr, Radarr, Prowlarr, FlareSolverr
- Download Clients: qBittorrent, RDT-Client, Zurg+rclone, SABnzbd, Recyclarr
- Agent Layer: agent-api (FastAPI 8880), agent-worker, agent-qc, agent-storage, iptv-gateway
- Infra: Postgres 16, Redis 7, socket-proxy
- Observability: Prometheus, Loki, Promtail, Grafana

**Tech Stack:** Python 3.12, FastAPI+uvicorn, SQLAlchemy 2.0 async+asyncpg, Postgres 16, Redis 7, httpx, Alembic, Traefik v3.3, React/Vite PWA.

**Job Pipeline:** Request -> agent-api -> worker resolves TMDB ID -> searches Prowlarr -> regex+scoring -> acquire (RD first, torrent fallback) -> import -> qc -> Jellyfin scan -> DONE.

**Key Files:** `invisible-arr/edge-node/` (root), `docker-compose.yml`, `services/shared/`, agent services, iptv-gateway.

---

## Workflow Skills

These are structured workflows. Use them as checklists when the situation matches.

### 1. Brainstorming (Before any creative/feature work)
Explore intent before implementing.
1. Ask one clarifying question at a time
2. Propose 2-3 approaches with trade-offs
3. Present design sections for approval
4. Write design doc, then transition to planning

### 2. Writing Plans (Before multi-step implementation)
Write comprehensive plans assuming zero codebase context.
1. Create plan header: goal, architecture, tech stack
2. Structure as bite-sized tasks (2-5 min each)
3. Each task: write failing test -> verify fail -> implement -> verify pass -> commit
4. Include exact file paths, code snippets, expected commands

### 3. Test-Driven Development (For all implementations)
Write the test first. Watch it fail. Then implement.
1. Write failing test
2. Verify it fails correctly (not a false positive)
3. Write minimal implementation to pass
4. Verify it passes
5. Refactor while keeping tests green

### 4. Systematic Debugging (For any bug/failure)
Find root cause before attempting fixes.
- **Phase 1:** Read errors, reproduce, check recent changes, gather evidence
- **Phase 2:** Find working examples, compare patterns
- **Phase 3:** Form hypothesis, test minimally
- **Phase 4:** Create failing test, implement root cause fix
- Multiple failed fixes = architectural problem, step back

### 5. Verification Before Completion
Evidence before assertions.
1. Identify what command proves the claim
2. Run it fresh
3. Read full output
4. Verify it confirms the claim
5. THEN state the claim with evidence

### 6. Subagent-Driven Development (For plan execution)
One agent per task, two-stage review.
1. Read plan, extract all tasks
2. Per task: dispatch implementer -> spec reviewer -> code quality reviewer
3. Loop on issues until verified
4. Final code review across all tasks

### 7. Parallel Agent Dispatch (For 2+ independent tasks)
1. Identify independent problem domains
2. Create focused agent tasks with clear scope and constraints
3. Dispatch in parallel
4. Review results, verify no conflicts, run full test suite

### 8. Executing Plans
1. Load plan file, review critically
2. Execute tasks in batches of 3
3. Mark progress, run verifications
4. Report per batch, apply feedback

### 9. Finishing a Development Branch
1. Verify all tests pass
2. Determine base branch
3. Choose: merge locally, create PR, keep as-is, or discard
4. Execute with appropriate git commands

### 10. Code Review (Requesting)
1. Get git SHAs for the change
2. Dispatch reviewer with: what was implemented, plan/requirements, base/head, description
3. Fix critical issues immediately, important before proceeding, minor later

### 11. Code Review (Receiving)
1. Read feedback without reacting
2. Restate requirement or ask clarification
3. Verify against codebase
4. Respond with technical acknowledgment or reasoned pushback
5. Implement one-by-one with testing

### 12. Git Worktrees (For isolated feature work)
1. Check existing worktree directories
2. Create worktree: `git worktree add <path> -b <branch>`
3. Run project setup
4. Verify tests pass before starting work

### 13. Frontend Design (For UI work)
Create distinctive interfaces, avoid generic AI aesthetics.
1. Define purpose, tone, constraints
2. Choose bold aesthetic direction
3. Identify one unforgettable differentiator
4. Implement with meticulous attention to typography, color, motion, spacing

### 14. Playground Builder (For interactive HTML tools)
Self-contained single-file HTML explorers.
1. Identify playground type
2. Use state management pattern: single state object, controls write, render reads
3. Include sensible defaults and 3-5 presets
4. Generate natural-language prompt output

---

## MCP Servers & External Tools

These are running tool servers accessible via MCP protocol. If your platform supports MCP, connect to these. Otherwise, use equivalent APIs directly.

### Available MCP Servers

| Server | What It Does | Direct Alternative |
|--------|-------------|-------------------|
| **Context7** | Up-to-date library docs and code examples | Check official docs manually |
| **Playwright** | Browser automation (click, navigate, screenshot, fill forms, etc.) | Selenium, Puppeteer |
| **Canva** | Design creation, editing, export, asset management | Canva API directly |
| **Indeed** | Job search, company data, resume management | Indeed API |
| **Vercel** | Deploy, manage projects, check domains, view logs | Vercel CLI / API |

### Context7 Usage
- `resolve-library-id` - Find the Context7 ID for a library
- `query-docs` - Get up-to-date docs/examples for any library

### Playwright Usage (Browser Automation)
- `browser_navigate` - Go to URL
- `browser_click` / `browser_fill_form` / `browser_type` - Interact
- `browser_snapshot` / `browser_take_screenshot` - Capture state
- `browser_evaluate` / `browser_run_code` - Execute JS
- `browser_wait_for` / `browser_network_requests` - Monitor

### Canva Usage
- `generate-design` / `generate-design-structured` - Create designs from prompts
- `start-editing-transaction` -> `perform-editing-operations` -> `commit-editing-transaction` - Edit designs
- `export-design` / `get-design-thumbnail` - Export
- `search-designs` / `list-folder-items` - Browse

### Vercel Usage
- `deploy_to_vercel` - Deploy projects
- `list_projects` / `get_project` - Manage projects
- `get_deployment` / `get_deployment_build_logs` / `get_runtime_logs` - Debug deployments
- `check_domain_availability_and_price` - Domain management

---

## Enabled Plugins (Claude Code Specific)

These plugins provide skills and capabilities within Claude Code. For other agents, the equivalent workflows are documented in the Skills section above.

- **superpowers** v4.3.1 - Brainstorming, planning, TDD, debugging, verification, parallel agents
- **frontend-design** - Production-grade UI design skill
- **playground** - Interactive HTML tool builder
- **feature-dev** - Code architecture, exploration, and review agents
- **code-review** - Pull request review
- **code-simplifier** - Code clarity and refactoring
- **sentry** - Error monitoring, SDK setup, issue workflows
- **context7** - Library documentation lookup
- **playwright** - Browser automation
- **commit-commands** - Git commit, push, PR workflows
- **claude-md-management** - CLAUDE.md file management
- **ralph-loop** - Iterative development loop
- **security-guidance** - Security best practices
- **semgrep** - Static analysis
- **serena** - Code intelligence
- **supabase** - Supabase integration
- **github** - GitHub integration
- **pyright-lsp** / **typescript-lsp** - Language server support

---

## Usage Notes for Gemini

- Load this file as system instructions or upload as context when starting a session
- Gemini has growing MCP support via extensions - connect where possible
- For browser automation, use Gemini's built-in browsing or connect Playwright MCP
- Follow the same plan-first, verify-last discipline
- Reference `tasks/todo.md` and `tasks/lessons.md` for shared state

### Token-Efficient Tips
- Don't load this entire file every message. Load the relevant section.
- For routine tasks, skip to the specific workflow skill needed.
- Keep `tasks/todo.md` as the shared state file - all agents read/write it.
- Use `tasks/lessons.md` as persistent memory across agents.

### Making It Work Offline (No Claude Available)
1. This file contains all workflows as plain markdown checklists
2. Any AI can follow them as structured prompts
3. The MCP servers run independently - connect any MCP client
4. Project context in the Project Context section is self-contained

---

*Generated by Claude Code. Update this file when skills or MCP servers change.*
