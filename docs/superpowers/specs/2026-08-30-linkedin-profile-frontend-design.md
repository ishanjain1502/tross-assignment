# LinkedIn Profile Parser Frontend — Design Spec

## Goal

Minimal browser UI to submit comma-separated LinkedIn profile URLs and display structured scrape results.

## Architecture

- Vanilla HTML/CSS/JS in `frontend/`, served by FastAPI `StaticFiles`
- Unauthenticated UI proxy at `/api/v1/ui/*` uses server-side API key (local dev)
- Existing async job queue unchanged; frontend polls per profile

## UI

1. Comma-separated URL input
2. Per-URL progress badges (queued → processing → done/failed)
3. Profile cards showing: name, headline, location, about, experience, education, skills, certifications, languages, profile/background images

## Out of scope

API key input, user auth, export, webhooks
