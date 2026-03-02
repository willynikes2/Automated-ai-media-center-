# Security & Code Quality Audit — Invisible Arr + Agent Brain v1

> Paste this into Claude Code while inside the `Automated-ai-media-center-/invisible-arr/` directory.

---

## ROLE

You are a senior security engineer and Python code reviewer. Audit the entire Invisible Arr + Agent Brain v1 codebase for security vulnerabilities, bugs, code quality issues, and deployment risks. Be thorough and brutal — this is going to production and handling API tokens, user data, and network services.

## INSTRUCTIONS

Read every file in this repository. Perform ALL of the following audits, then produce a final report with findings categorized by severity (CRITICAL / HIGH / MEDIUM / LOW / INFO).

---

## AUDIT 1: SECRETS & CREDENTIAL SAFETY

Check for:
- Hardcoded API keys, tokens, passwords, or secrets anywhere in source code
- `.env` or `.env.template` accidentally containing real credentials
- Secrets logged to stdout/stderr (print statements, logging calls that dump tokens)
- API tokens passed in URL query strings instead of headers (especially RD token)
- Missing `.gitignore` entries that could leak secrets (`.env`, config dirs, database files)
- Docker Compose env vars that could leak in `docker inspect` output
- Postgres password handling — is it generated securely? Is it ever logged?
- Redis running without auth (default config has no password)
- Any file that writes secrets to disk in plaintext

Fix: Add `REDIS_PASSWORD` to `.env.template` and configure Redis with `--requirepass`. Ensure no secret ever appears in a log line.

---

## AUDIT 2: INPUT VALIDATION & INJECTION

Check every API endpoint for:
- SQL injection via unsanitized user input (even with SQLAlchemy ORM — check any raw queries)
- Path traversal in file operations (especially import_files, movie_path, tv_path — can a crafted title write outside /data/media?)
- Command injection via ffprobe subprocess call (does file_path get shell-escaped?)
- XMLTV/M3U parsing — can a malicious M3U or XMLTV payload cause XXE (XML External Entity) attacks?
- Missing request body validation (Pydantic models should reject unexpected fields)
- Missing length limits on string inputs (title, query, URLs — could someone send a 10MB title?)
- user_token in query string for IPTV endpoints — is it validated? Can it be brute-forced?
- Webhook endpoint (/v1/webhooks/arr) — does it validate the source? Can anyone POST to it?

Fix every issue found. For path traversal, sanitize and validate that final paths are within the expected directory. For subprocess calls, use list arguments (never shell=True). For XML parsing, disable external entity resolution in lxml.

---

## AUDIT 3: AUTHENTICATION & AUTHORIZATION

Check:
- Is there ANY authentication on agent-api endpoints? If not, anyone who finds the port can create jobs, read all jobs, change prefs
- user_token for IPTV — how is it generated? Is it a secure random token or predictable?
- API key generation for users — is it using `secrets.token_urlsafe()` or something weak?
- Are there any endpoints that should require auth but don't?
- Is there rate limiting on any endpoint? (Missing rate limiting = abuse vector)
- CORS settings — is it `allow_origins=["*"]`? That's fine for dev but dangerous in production
- Traefik config — are the internal services truly unreachable from outside?

Fix: Add API key middleware to all /v1/* endpoints. Add rate limiting (at minimum on /v1/request and IPTV playlist endpoints). Fix CORS for production.

---

## AUDIT 4: DOCKER & DEPLOYMENT SECURITY

Check docker-compose.yml for:
- Containers running as root unnecessarily
- Unnecessary capability grants (only gluetun needs NET_ADMIN)
- Volumes mounted read-write that should be read-only
- Missing healthchecks on any service
- Missing restart policies
- Docker socket mounted to any container other than Traefik (massive security risk)
- Network isolation — are internal services on the same network as public-facing ones? Should there be separate networks?
- Image tags using `:latest` (not pinned — could break on update)
- Missing resource limits (memory/CPU) — one container could OOM the whole VPS

Check install.sh for:
- Running as root without warning
- Using `curl | sh` patterns without hash verification
- `sed -i` on .env with user input — shell injection possible?
- Missing input validation on prompted values

Check smoke.sh for:
- Secrets appearing in test output
- Using `set -x` which would echo secrets

Fix: Add Docker networks (frontend for Traefik-exposed, backend for internal). Pin image versions. Add memory limits. Add `read_only: true` where possible. Validate install.sh inputs.

---

## AUDIT 5: PYTHON CODE QUALITY

Check all Python files for:
- Missing error handling (bare `except:` or no try/except on network calls)
- Resource leaks (unclosed httpx clients, database sessions not closed on error)
- Race conditions in the worker (what if two workers grab the same job?)
- Missing timeouts on ALL external HTTP calls (RD, Prowlarr, TMDB) — a hung call blocks the worker forever
- Async anti-patterns (blocking calls inside async functions, missing `await`)
- Import errors (circular imports between shared modules)
- Missing `__init__.py` files
- Unused imports
- Type hint inconsistencies
- f-strings with user input that could cause format string issues
- Any use of `eval()`, `exec()`, `pickle.loads()`, or `yaml.load()` (without safe loader)
- Missing database transaction handling (partial writes on error)
- Job state machine — can a job get stuck? Are there timeout/cleanup mechanisms for zombie jobs?
- RD polling loop — what's the max timeout? Is there a circuit breaker if RD is down?
- Download function — does it verify file integrity? What if the download is partial?

Fix all issues. Add timeouts to every httpx call (30s default, 300s for downloads). Add job timeout/cleanup. Add circuit breakers.

---

## AUDIT 6: DEPENDENCY SECURITY

Check all requirements.txt files for:
- Are versions pinned? (They should be for reproducible builds)
- Are there any known CVEs in the specified versions?
- Are there unnecessary dependencies?
- Is there a dependency that pulls in something dangerous?

Fix: Pin all versions. Remove unnecessary deps.

---

## AUDIT 7: DATA PRIVACY & COMPLIANCE

Check:
- Is user data (API keys, tokens, viewing history via jobs table) encrypted at rest?
- Are database backups configured?
- Can one user see another user's jobs, prefs, or IPTV channels?
- Is there a user deletion/data export path? (GDPR consideration for SaaS)
- Are RD API tokens stored per-user or globally? If globally, all users share one RD account (fine for v1 but document it)
- Job events — do they log sensitive data (magnet links, download URLs)?
- Access logs — does Traefik log user IPs? Is log rotation configured?

---

## AUDIT 8: ERROR HANDLING & RESILIENCE

Check:
- What happens if Postgres is down when agent-api starts?
- What happens if Redis is down when a job is created?
- What happens if Prowlarr returns 500 during a search?
- What happens if RD API is unreachable mid-download?
- What happens if disk is full during import?
- What happens if ffprobe hangs forever?
- What happens if the IPTV source URL is unreachable?
- Are there retry mechanisms with exponential backoff?
- Is there a dead letter queue for permanently failed jobs?
- Can the system recover gracefully from a full Docker restart?

---

## AUDIT 9: PERFORMANCE & SCALABILITY

Check:
- N+1 query patterns (loading jobs then loading events one by one)
- Missing database indexes (job.state, job.user_id, job.created_at, blacklist.release_hash)
- XMLTV parsing — is the entire EPG loaded into memory? For large EPGs this could be 100MB+
- M3U parsing — same concern with large playlists
- Redis caching — is the EPG cache key specific enough? Could one user's cache poison another's?
- Are database connections pooled?
- Is there connection pool exhaustion possible under load?

---

## OUTPUT FORMAT

After completing all 9 audits, produce:

### 1. FINDINGS TABLE

For each finding:
| ID | Severity | Audit | File:Line | Description | Fix |
|----|----------|-------|-----------|-------------|-----|

### 2. FIXES APPLIED

For each fix you make, show:
- File modified
- What changed (before/after or description)
- Which finding ID it addresses

### 3. REMAINING RISKS

Issues that need human decision or can't be auto-fixed:
- Architecture decisions
- Third-party dependency risks
- Operational procedures needed

### 4. HARDENING CHECKLIST

A checklist the developer should complete before production:
- [ ] Change all default passwords
- [ ] Set up TLS via domain + Let's Encrypt
- [ ] Configure firewall (ufw)
- [ ] Set up log rotation
- [ ] Set up automated backups
- [ ] Pin Docker image versions to specific SHAs
- [ ] Set up monitoring (uptime checks at minimum)
- [ ] Review and restrict CORS origins
- [ ] Enable Redis AUTH
- [ ] Add rate limiting
- [ ] Set up fail2ban for SSH

---

## CRITICAL RULE

Do NOT just list problems. **Fix every fixable issue directly in the code.** Edit the files. Only list things in "Remaining Risks" if they truly require a human decision or external action. I want to `git diff` after this audit and see real improvements pushed to the repo.
