# Voyager Endpoint Validation Guide

LinkedIn does **not** publish documentation for the Voyager API (`www.linkedin.com/voyager/api/...`). The paths in `linkedin_endpoints.yaml` are reverse-engineered starting points, not confirmed against official docs.

Use this guide to validate and update endpoints when building or debugging the scraper.

---

## Why official LinkedIn docs do not apply

| Official API | Voyager (this project) |
|---|---|
| Host: `api.linkedin.com` | Host: `www.linkedin.com` |
| OAuth access tokens | Browser session cookies (`li_at`, `JSESSIONID`) |
| `/v2/me`, `/rest/identityMe` | `/voyager/api/me`, `/voyager/api/graphql` |
| Authenticated member only (mostly) | Arbitrary public profile URLs |
| Documented on [Microsoft Learn](https://learn.microsoft.com/en-us/linkedin/) | Undocumented; discovered via network traffic |

The assignment requires reverse engineering Voyager, not switching to the public API.

---

## When to validate

- Before first live scrape (after Segment 6+ auth is wired)
- After LinkedIn UI changes or scrape failures (401, 403, 404, 500)
- After long gaps between development sessions (decoration IDs and query hashes rotate)
- Before deployment or demo

---

## Manual validation (browser DevTools)

### 1. Capture a fresh session

1. Log into [linkedin.com](https://www.linkedin.com) in Chrome/Edge.
2. Open DevTools → **Application** → **Cookies** → `https://www.linkedin.com`.
3. Copy `li_at` and `JSESSIONID` into `.env` (never commit these).

### 2. Record network traffic on a profile page

1. DevTools → **Network** tab.
2. Enable **Preserve log**.
3. Filter by `voyager` or `graphql`.
4. Navigate to a known public profile, e.g. `https://www.linkedin.com/in/<username>`.
5. Scroll the page to load experience, education, and skills sections.

### 3. Compare captured requests to `linkedin_endpoints.yaml`

For each relevant request, check:

| Field | Where to look | Update in YAML if changed |
|---|---|---|
| REST path | Request URL path | `rest_endpoints.*` |
| GraphQL path | `/voyager/api/graphql` | `rest_endpoints.graphql` |
| `decorationId` | Query string or variables | `graphql.decoration_ids.full_profile` |
| `queryId` | GraphQL query string param | Add/update in `graphql` section if used |
| `Accept` header | Request headers | `required_headers.accept` |
| `User-Agent` | Request headers | `required_headers.user_agent` |
| `X-Restli-Protocol-Version` | Request headers | `required_headers.x_restli_protocol_version` |
| Profile ID in HTML | View page source / initial HTML response | `profile_id_patterns` |

### 4. Sanity-check session endpoint

In Network, find a successful call to `/voyager/api/me` (or trigger it by refreshing the feed).

- **200** with profile JSON → session cookies are valid.
- **401/403** → cookies expired or account restricted; re-extract session.

### 5. Sanity-check profile fetch

Look for requests matching patterns like:

- `/voyager/api/identity/profiles/...`
- `/voyager/api/identity/dash/profiles/...`
- `/voyager/api/graphql?...` with profile-related variables

Confirm the response includes fields you need: `firstName`, `lastName`, `headline`, `positions`, `educations`, `skills`, etc.

---

## What to update in `linkedin_endpoints.yaml`

```yaml
# Typical updates after validation:

rest_endpoints:
  profile: "/voyager/api/identity/profiles/{profile_id}"   # path may shift to dash/*
  graphql: "/voyager/api/graphql"

graphql:
  decoration_ids:
    full_profile: "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-XX"  # version number changes

profile_id_patterns:
  - name: "fsd_profile_urn"
    pattern: 'urn:li:fsd_profile:([A-Za-z0-9_-]+)'   # add patterns seen in live HTML/JSON
```

Also update the comment at the top of the YAML:

```yaml
# Last verified: YYYY-MM-DD (manual DevTools capture)
```

---

## Common failure signals

| Symptom | Likely cause | Fix |
|---|---|---|
| 401 / 403 on all Voyager calls | Expired or invalid cookies | Re-extract `li_at` + `JSESSIONID` |
| 404 on profile endpoint | Wrong path or profile ID format | Re-check DevTools; update `rest_endpoints` |
| 500 on GraphQL | Stale `decorationId` or `queryId` | Copy current values from browser request |
| Empty `included[]` / partial data | Wrong URN or missing section params | Compare full GraphQL variables from browser |
| Profile ID not resolved | HTML structure changed | Add/update `profile_id_patterns` |

---

## Programmatic smoke test (after auth segment)

Once `app/linkedin/` auth and client code exist, run a minimal live check:

```bash
# From project root (requires valid .env cookies)
PYTHONPATH=. python scripts/smoke_test_voyager.py
```

Expected flow (to implement in a later segment):

1. Call `/voyager/api/me` → confirm session
2. Resolve a test profile URL → internal ID
3. Fetch one profile section → confirm non-empty JSON

If no smoke script exists yet, use DevTools validation above.

---

## Documentation references (official — for contrast only)

These describe the **public** API, not Voyager:

- [Profile API (`/v2/me`)](https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api)
- [identityMe (`/rest/identityMe`)](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/verified-on-linkedin/api-reference/identity-me)
- [Rest.li protocol version header](https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/protocol-version)

Do **not** expect Voyager paths to appear in these docs.

---

## README / known limitations (suggested wording)

When documenting the project for reviewers:

> Endpoint paths and GraphQL decoration IDs are reverse-engineered from LinkedIn's internal Voyager API. They are not documented by LinkedIn and may change without notice. Validation is performed via browser network capture, not official API documentation.

---

## Checklist (copy per validation run)

- [ ] Fresh `li_at` and `JSESSIONID` in `.env`
- [ ] `/voyager/api/me` returns 200 in DevTools
- [ ] Profile page triggers expected Voyager/GraphQL requests
- [ ] REST paths match `config/linkedin_endpoints.yaml`
- [ ] `decorationId` / `queryId` values match live traffic
- [ ] Required headers match live traffic
- [ ] Profile ID extraction patterns work on sample URLs
- [ ] `Last verified` date updated in YAML
- [ ] Changes committed (YAML only — never cookies)
