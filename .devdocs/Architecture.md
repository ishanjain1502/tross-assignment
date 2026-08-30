# System Architecture

## Overview

The LinkedIn Profile API is a Docker Compose stack with three runtime services: **API** (FastAPI + static web UI), **Worker** (background scrape processor), and **PostgreSQL** (job queue + profile cache).

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           CLIENT ENTRY POINTS                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Browser (local dev)              API clients (production / scripts)      │
│       │                                    │                              │
│       ▼                                    ▼                              │
│  GET  /  (static UI)              POST /api/v1/scrape  + X-API-Key      │
│  POST /api/v1/ui/scrape           GET  /api/v1/scrape/{job_id}            │
│  GET  /api/v1/ui/scrape/{id}     (no API key on /health)                 │
│       │                                    │                              │
│       └────────────────┬───────────────────┘                              │
│                        ▼                                                  │
│              ┌─────────────────────┐                                        │
│              │   FastAPI (api)     │                                        │
│              │  routes.py          │  ← authenticated scrape API          │
│              │  ui_routes.py       │  ← UI proxy (server-side API key)    │
│              │  StaticFiles (/)   │  ← frontend/index.html, app.js      │
│              └──────────┬──────────┘                                        │
│                         │ create job / poll status                         │
│                         ▼                                                  │
│              ┌─────────────────────┐                                        │
│              │    PostgreSQL       │                                        │
│              │  jobs table (queue) │                                        │
│              │  profile cache      │                                        │
│              └──────────┬──────────┘                                        │
│                         │ poll queued jobs                                 │
│                         ▼                                                  │
│              ┌─────────────────────┐                                        │
│              │   Worker process    │                                        │
│              │  scraper_service    │                                        │
│              └──────────┬──────────┘                                        │
│                         │                                                  │
│                         ▼                                                  │
│              LinkedIn Voyager APIs (Dash → GraphQL → REST)                 │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

| Layer | Components | Responsibility |
|-------|------------|----------------|
| **Presentation** | `frontend/` (HTML/CSS/JS) | Comma-separated URL input, progress, profile result cards |
| **API** | `app/api/routes.py`, `app/api/ui_routes.py` | Job creation, status polling; UI proxy omits client auth |
| **Queue & cache** | PostgreSQL (`jobs` table, cache service) | Persist jobs, store scrape results |
| **Worker** | `app/workers/main.py` | Dequeue jobs, run scraper, update status |
| **LinkedIn client** | `app/linkedin/` | Auth, Dash/GraphQL/REST fetch, parse |

### Web UI data flow

1. User enters comma-separated profile URLs in the browser.
2. `frontend/app.js` validates URLs and POSTs each to `/api/v1/ui/scrape`.
3. API creates a job in PostgreSQL and returns `202` with `job_id`.
4. Frontend polls `/api/v1/ui/scrape/{job_id}` every ~2s until `completed` or `failed`.
5. Completed jobs render profile cards (name, headline, location, about, experience, education, skills, certifications, languages, images).

### Production note

In production (e.g. Vultr + Caddy), HTTPS terminates at Caddy and proxies to the API container on port 8000. Restrict or disable `/api/v1/ui/*` and the static UI mount if the instance is publicly reachable without additional access controls.

---

## Authentication Flow

LinkedIn session authentication used by the worker and API-backed scrape jobs:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AUTHENTICATION FLOW                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. GET https://www.linkedin.com/                                   │
│     ↓                                                                │
│     Returns: JSESSIONID cookie (contains CSRF token)                 │
│     Returns: li_at cookie (if previously logged in)                  │
│                                                                      │
│  2. Extract CSRF Token                                               │
│     ↓                                                                │
│     From JSESSIONID cookie value (after the pipe character)          │
│     OR from page meta tag                                            │
│                                                                      │
│  3. POST https://www.linkedin.com/uas/authenticate                  │
│     Headers:                                                         │
│       X-CSRF-Token: {csrf_token}                                     │
│       X-Requested-With: XMLHttpRequest                               │
│     Body: session_key={email}&session_password={password}            │
│            &csrfToken={csrf_token}                                   │
│     ↓                                                                │
│     Returns: li_at cookie (main auth token, ~6 month validity)       │
│              JSESSIONID (refreshed)                                  │
│                                                                      │
│  4. Subsequent API Calls                                             │
│     Headers:                                                         │
│       Cookie: li_at={token}; JSESSIONID={session}                    │
│       X-CSRF-Token: {from JSESSIONID}                                │
│       X-Restli-Protocol-Version: 2.0.0                               │
│       X-Li-Track: {"clientVersion":"3.0.0",...}                      │
│                                                                      │
│  Primary method: cookie extraction via scripts/extract_session.py   │
│  Fallback: credential login (often triggers CAPTCHA)                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```
