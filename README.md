# LinkedIn Profile API

A hosted HTTPS API and local web UI that accept LinkedIn profile URLs and return structured profile data (name, headline, location, about, experience, education, skills, certifications, languages, and images) by calling LinkedIn's internal Voyager APIs directly — **no browser automation**.

## Architecture

```
Browser UI (/)  ──→  /api/v1/ui/scrape  ──┐
                                           ├──→  PostgreSQL job queue
API client      ──→  /api/v1/scrape       ──┘         ↓
              (X-API-Key)                    Background worker polls queue
                                                        ↓
                              Resolve URL → Dash / GraphQL (primary) / REST (fallback)
                                                        ↓
                                              Parse → Cache → Return JSON
```

| Component | Technology |
|-----------|------------|
| API | FastAPI + Uvicorn |
| Web UI | Vanilla HTML/CSS/JS (served by FastAPI) |
| Queue & cache | PostgreSQL 16 |
| HTTP client | httpx (async) |
| Worker | Python async polling loop |
| Deployment | Docker Compose |

**Auth:** Cookie-based session (`li_at` + `JSESSIONID`) extracted from a logged-in browser. Credential login is supported as a fallback but often triggers CAPTCHA.

**Data source:** LinkedIn internal `/voyager/api/...` endpoints (reverse-engineered, not official LinkedIn developer APIs). See `config/ENDPOINT_VALIDATION.md` for how to validate endpoints via browser DevTools.

---

## Quick start (local)

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- Python 3.11+ (optional, for helper scripts)
- LinkedIn account (for session cookies)

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd tross-assignment

cp .env.example .env
```

Edit `.env`:

- Set a strong `API_KEY`
- Add real LinkedIn cookies (see [Session setup](#linkedin-session-setup))

### 2. Start the stack

```bash
docker compose up -d --build
```

### 3. Verify

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"healthy","version":"1.0.0"}`

### 4. Scrape profiles (web UI)

Open [http://localhost:8000](http://localhost:8000) in your browser.

1. Paste one or more LinkedIn profile URLs, **comma-separated**.
2. Click **Scrape profiles**.
3. Watch per-URL progress, then view structured results cards.

The UI calls unauthenticated proxy routes (`/api/v1/ui/*`) that use the server-side `API_KEY` from `.env` — no API key input in the browser.

### 5. Submit a scrape job (API / curl)

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"profile_url": "https://www.linkedin.com/in/johndoe/"}'
```

Poll for results:

```bash
curl http://localhost:8000/api/v1/scrape/<job_id> \
  -H "X-API-Key: YOUR_API_KEY"
```

---

## Web UI

A minimal static frontend lives in `frontend/` and is served by the API container at `/`.

| File | Purpose |
|------|---------|
| `frontend/index.html` | URL input, progress list, results container |
| `frontend/styles.css` | Profile cards, sections, responsive layout |
| `frontend/app.js` | Parse comma-separated URLs, submit jobs, poll, render |

**Displayed fields per profile:** name, headline, location, about, experience, education, skills, certifications, languages, profile image, and background image (when available).

**Input format:** comma-separated URLs, e.g.

```
https://www.linkedin.com/in/johndoe, https://www.linkedin.com/in/janedoe
```

A single URL works without a trailing comma. Invalid URLs are rejected before submission.

**Local dev auth:** The browser never sees `API_KEY`. `app/api/ui_routes.py` exposes thin proxy endpoints that delegate to the same job queue as the authenticated API. Intended for local development only — do not expose the UI proxy publicly in production without additional access controls.

---

## API reference

Authenticated endpoints (`/api/v1/scrape`) require the `X-API-Key` header. UI proxy endpoints (`/api/v1/ui/scrape`) do not — they rely on the server-side key and are meant for the bundled web UI.

### `GET /health`

Health check (no API key required).

**Response:** `200 OK`

```json
{"status": "healthy", "version": "1.0.0"}
```

### `POST /api/v1/scrape`

Submit a profile URL for scraping.

**Request body:**

```json
{
  "profile_url": "https://www.linkedin.com/in/username",
  "webhook_url": "https://optional-callback.example.com/hook",
  "include_fields": ["profile", "experience", "education", "skills"]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `profile_url` | Yes | Public LinkedIn profile URL (`/in/username`) |
| `webhook_url` | No | Reserved for future webhook delivery |
| `include_fields` | No | Subset of sections to return |

**Response:** `202 Accepted`

```json
{
  "job_id": "uuid",
  "status": "queued",
  "estimated_wait_seconds": 5,
  "poll_url": "/api/v1/scrape/uuid"
}
```

### `GET /api/v1/scrape/{job_id}`

Poll job status or retrieve results.

**Queued / processing:**

```json
{
  "job_id": "uuid",
  "status": "queued",
  "created_at": "2026-08-30T10:00:00+00:00"
}
```

**Completed:**

```json
{
  "job_id": "uuid",
  "status": "completed",
  "duration_ms": 3200,
  "from_cache": false,
  "scraped_at": "2026-08-30T10:00:05+00:00",
  "data": {
    "profile": { "first_name": "...", "headline": "...", "..." : "..." },
    "experience": [],
    "education": [],
    "skills": [],
    "certifications": [],
    "languages": [],
    "warnings": [],
    "scraped_at": "...",
    "source": "graphql"
  }
}
```

**Failed:**

```json
{
  "job_id": "uuid",
  "status": "failed",
  "error": {
    "code": "SESSION_EXPIRED",
    "message": "..."
  }
}
```

### `POST /api/v1/ui/scrape`

Local web UI proxy — same request/response as `POST /api/v1/scrape`, but **no `X-API-Key` header**. Uses `API_KEY` from server environment.

### `GET /api/v1/ui/scrape/{job_id}`

Local web UI proxy — same response shapes as `GET /api/v1/scrape/{job_id}`, but **no `X-API-Key` header**.

---

## LinkedIn session setup

Cookie auth is the recommended approach.

1. Log into [linkedin.com](https://www.linkedin.com) in Chrome or Firefox.
2. Open DevTools → **Application** → **Cookies** → `https://www.linkedin.com`.
3. Copy `li_at` and `JSESSIONID`.
4. Run the helper script:

```bash
python scripts/extract_session.py
```

Or set them manually in `.env`:

```env
LINKEDIN_LI_AT=...
LINKEDIN_JSESSIONID=...
```

After updating cookies, restart the worker and API:

```bash
docker compose restart api worker
```

---

## Deploy on a Vultr VM (production)

These steps deploy the full stack on an Ubuntu 22.04/24.04 cloud instance with HTTPS via Caddy.

### Recommended VM specs

| Setting | Value |
|---------|-------|
| Provider | [Vultr](https://www.vultr.com) |
| OS | Ubuntu 22.04 LTS or 24.04 LTS |
| Plan | 2 vCPU / 2 GB RAM minimum |
| Region | Closest to your users |

### Step 1 — Create the Vultr instance

1. Log into Vultr → **Deploy** → **Cloud Compute**.
2. Choose **Ubuntu 22.04 LTS** (or 24.04).
3. Select a $12/mo (2 GB) plan or higher.
4. Under **SSH Keys**, add your public key (recommended over password-only).
5. Deploy and note the **public IP address**.

### Step 2 — Point DNS to the VM

Create an **A record** for your API subdomain:

```
api.yourdomain.com  →  <VULTR_VM_IP>
```

Wait for DNS propagation (usually a few minutes).

### Step 3 — SSH into the server

```bash
ssh root@<VULTR_VM_IP>
```

### Step 4 — Install Docker

```bash
apt update && apt upgrade -y
apt install -y ca-certificates curl git ufw

curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker
```

Verify:

```bash
docker compose version
```

### Step 5 — Configure firewall

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

Do **not** expose PostgreSQL (port 5433) or the raw API port (8000) publicly — Caddy will proxy HTTPS to localhost.

### Step 6 — Clone the project

```bash
cd /opt
git clone <your-repo-url> linkedin-api
cd linkedin-api
```

### Step 7 — Create production `.env`

```bash
cp .env.example .env
nano .env
```

Set at minimum:

```env
LINKEDIN_LI_AT=<from browser>
LINKEDIN_JSESSIONID=<from browser>
API_KEY=<long-random-secret>
LOG_LEVEL=INFO
CACHE_TTL_HOURS=24
```

Generate a strong API key:

```bash
openssl rand -hex 32
```

**Security:** Never commit `.env` to git. Restrict file permissions:

```bash
chmod 600 .env
```

### Step 8 — Harden Docker Compose for production (recommended)

Before starting, edit `docker-compose.yml` and **remove the Postgres host port mapping** so the database is only reachable inside the Docker network:

```yaml
  postgres:
    # Remove or comment out:
    # ports:
    #   - "5433:5432"
```

Optionally change the default Postgres password in `docker-compose.yml` and update `DATABASE_URL` in the `api` and `worker` services to match.

### Step 9 — Start the application

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=50
```

Confirm all three services are healthy: `linkedin_postgres`, `linkedin_api`, `linkedin_worker`.

Test locally on the VM:

```bash
curl http://127.0.0.1:8000/health
```

### Step 10 — Install Caddy for HTTPS

Caddy automatically provisions Let's Encrypt certificates.

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy
```

Create `/etc/caddy/Caddyfile`:

```caddy
api.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
```

Replace `api.yourdomain.com` with your actual domain.

Reload Caddy:

```bash
systemctl reload caddy
systemctl enable caddy
```

### Step 11 — Verify public HTTPS access

From your local machine:

```bash
curl https://api.yourdomain.com/health
```

Submit a test scrape:

```bash
curl -X POST https://api.yourdomain.com/api/v1/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"profile_url": "https://www.linkedin.com/in/johndoe/"}'
```

The web UI is also available at `https://api.yourdomain.com/` if you keep the static file mount enabled. For production, consider restricting access to `/` and `/api/v1/ui/*` (e.g. IP allowlist, basic auth in Caddy, or removing `ui_routes` registration) since those endpoints do not require a client API key.

### Step 12 — Enable auto-restart on reboot

Docker Compose services use `restart: unless-stopped`. Ensure Docker starts on boot:

```bash
systemctl is-enabled docker
```

---

## Operations

### View logs

```bash
docker compose logs -f api
docker compose logs -f worker
```

### Restart after cookie refresh

```bash
docker compose restart api worker
```

### Update deployment

```bash
cd /opt/linkedin-api
git pull
docker compose up -d --build
```

### Reset stuck jobs

If jobs are stuck in `processing`:

```bash
docker compose exec postgres psql -U linkedin -d linkedin_api \
  -c "UPDATE jobs SET status='queued' WHERE status='processing';"
```

### Backup Postgres volume

```bash
docker compose exec postgres pg_dump -U linkedin linkedin_api > backup.sql
```

---

## Approach

This project reverse-engineers LinkedIn's internal **Voyager API** (the same HTTP/GraphQL calls the website makes) instead of using browser automation or LinkedIn's limited public developer APIs.

1. **Async job queue** — Scraping takes 2–5 seconds per profile; clients get a job ID immediately and poll for results.
2. **Dash / GraphQL-first** — Profile sections are fetched via LinkedIn's internal Dash and GraphQL endpoints; REST endpoints are used as fallback.
3. **PostgreSQL-backed cache** — Profiles are cached with a configurable TTL (default 24 hours) to reduce LinkedIn requests.
4. **Externalized endpoints** — Voyager paths and GraphQL decoration IDs live in `config/linkedin_endpoints.yaml` so they can be updated without code changes when LinkedIn rotates internal APIs.
5. **Cookie auth** — Session cookies from a real browser login avoid CAPTCHA issues common with credential-based login.
6. **Static UI + server proxy** — A vanilla HTML/CSS/JS frontend is served by FastAPI with no build step. The UI talks to `/api/v1/ui/*` proxy routes so credentials stay server-side during local development.

---

## Known limitations

| Limitation | Details |
|------------|---------|
| **Unofficial API** | Voyager endpoints are undocumented and can change without notice. Validate via DevTools (`config/ENDPOINT_VALIDATION.md`). |
| **Session expiry** | `li_at` cookies expire (~6 months). Re-run `scripts/extract_session.py` when auth fails. |
| **Rate limiting** | LinkedIn may throttle or block aggressive scraping. The worker backs off on 429 responses. |
| **Private / restricted profiles** | Profiles with restricted visibility may return partial data or errors. |
| **Terms of Service** | Automated access may violate LinkedIn's ToS. Use at your own risk with a non-primary account. |
| **No official API parity** | Public LinkedIn APIs cannot fetch arbitrary full profiles; this project intentionally uses reverse engineering per assignment requirements. |
| **Decoration ID drift** | GraphQL `decorationId` values rotate; update `config/linkedin_endpoints.yaml` when GraphQL returns 500 errors. |
| **UI proxy exposure** | `/api/v1/ui/*` has no client auth. Restrict or disable it when deploying the API publicly. |

---

## Project structure

```
app/
  api/routes.py          # Authenticated scrape API (X-API-Key)
  api/ui_routes.py       # Unauthenticated UI proxy (local dev)
  linkedin/              # Voyager client, auth, parsers
  services/              # Job queue, cache, scraper orchestration
  workers/main.py        # Background worker
  main.py                # FastAPI entrypoint + static file mount
frontend/
  index.html             # Web UI shell
  styles.css             # Profile card styles
  app.js                 # Submit, poll, render logic
config/
  linkedin_endpoints.yaml
scripts/
  extract_session.py     # Cookie setup helper
  check_config.py
  init_db.py
docker-compose.yml
Dockerfile.api
Dockerfile.worker
```

---

## Development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Start Postgres (or use docker compose up -d postgres)
PYTHONPATH=. python scripts/init_db.py

# Terminal 1 — API (serves http://localhost:8000 UI + API)
DATABASE_URL=postgresql+asyncpg://linkedin:linkedin@localhost:5433/linkedin_api \
  PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# Terminal 2 — Worker
DATABASE_URL=postgresql+asyncpg://linkedin:linkedin@localhost:5433/linkedin_api \
  PYTHONPATH=. python -m app.workers.main
```

Open [http://localhost:8000](http://localhost:8000) for the web UI, or use the authenticated API at `/api/v1/scrape` with `X-API-Key`.

---

## License

Assignment / educational project. Review LinkedIn's Terms of Service before production use.
