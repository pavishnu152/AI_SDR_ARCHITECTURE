# Deployment Guide

## Why Render, not Railway

Both were on the table in the original tech stack decision (docs/architecture.md
§4). Checked current pricing before committing to one (2026-08-08):

- **Render**: a genuine recurring free tier — 750 hrs/month compute for web
  services (they sleep after 15 min idle, ~30-60s cold start on the next
  request), Docker as a first-class deploy method, no credit card required
  to start. Free Postgres is real but time-boxed: 1GB storage, expires 30
  days after creation with a 14-day grace period before deletion.
- **Railway**: as of 2026 its "free tier" is a one-time $5 usage credit, not
  a recurring allowance — after that it's a minimum $5/mo Hobby plan billed
  by the second for CPU/memory/storage/egress.

For a portfolio project meant to stay live and linkable without an ongoing
bill, Render's recurring free tier is the better fit. The Postgres 30-day
expiry is a real limitation either way — see "Keeping the demo alive"
below.

Sources checked: render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026,
kuberns.com/blogs/render-postgres-pricing-setup-limits, srvrlss.io/provider/railway.

## What's already done

`render.yaml` at the repo root is a Render Blueprint — one file that
defines all three pieces:

1. `ai-sdr-api` — the FastAPI backend, built from `docker/Dockerfile` (the
   same Dockerfile verified in Milestone 11/12, no changes needed for
   Render specifically).
2. `ai-sdr-dashboard` — the React frontend, built as a static site from
   `frontend/` via `npm install && npm run build`, served from
   `frontend/dist`.
3. `ai-sdr-db` — a managed Postgres instance on the free plan.

Its schema was checked against Render's actual Blueprint YAML reference
(fetched live on 2026-08-08, not written from memory) — `plan: free`,
`runtime: docker`/`runtime: static`, `fromDatabase`, `generateValue`,
`sync: false`, and the static-site SPA rewrite rule are all real,
current fields, not guessed.

## What you need to do (this part can't be done from this sandbox — it
## needs your own Render account and API key)

1. **Push this repo to GitHub** (if you haven't already — see the standing
   git-commit backlog note from earlier milestones; commit everything
   first).
2. **Create a Render account** at [dashboard.render.com/register](https://dashboard.render.com/register)
   — no credit card needed for the free tier.
3. **New > Blueprint**, connect your GitHub repo. Render detects
   `render.yaml` automatically and shows you the three resources it's
   about to create.
4. Render will prompt for the one secret marked `sync: false` in
   `render.yaml`: **`ANTHROPIC_API_KEY`**. Paste your real key here — it's
   never committed to the repo.
5. Click **Apply**. First deploy takes a few minutes (Docker build +
   `alembic upgrade head` via `docker/entrypoint.sh`, then the static site
   build).

## The two-pass step (a real constraint, documented rather than hidden)

The API needs to know the dashboard's URL (for `CORS_ALLOWED_ORIGINS`) and
the dashboard needs to know the API's URL (for `VITE_API_BASE_URL`) — but
Render only assigns each service's `https://<name>.onrender.com` URL once
it exists, and if `ai-sdr-api` or `ai-sdr-dashboard` is already taken by
another Render account, yours will get a suffixed name instead (e.g.
`ai-sdr-api-a1b2.onrender.com`).

After the first deploy finishes:

1. Note the two actual URLs from the Render dashboard.
2. If either differs from the `render.yaml` guess:
   - API service → Environment tab → update `CORS_ALLOWED_ORIGINS` to the
     real dashboard URL.
   - Dashboard service → Environment tab → update `VITE_API_BASE_URL` to
     the real API URL, then **trigger a manual redeploy** (Vite bakes this
     value in at build time — an env var edit alone doesn't take effect
     until the next build).
3. Re-test: open the dashboard URL, register a user, log in, research a
   lead.

## Keeping the demo alive

The free Postgres instance expires 30 days after creation (14-day grace
period after that). For a portfolio project you want linkable indefinitely,
either:

- Recreate the database (and re-run `alembic upgrade head`) before it
  expires, accepting the data loss, or
- Upgrade just the database to `basic-256mb` (a few dollars/month at time
  of writing) and leave the web services on the free plan — the app itself
  doesn't need paid compute, only persistent storage does.

The free web services sleeping after 15 minutes of inactivity is normal
and fine for a demo — the first request after idle takes ~30-60s to wake
up; mention this if you're walking someone through it live.

## Verifying a deploy without live access to it

This sandbox can't create a Render account or click deploy on your behalf,
so the render.yaml schema was checked against Render's real, current docs
rather than run end-to-end. Once you deploy, the fastest sanity check:

```bash
curl https://<your-api>.onrender.com/health
# expect: {"status":"ok","env":"production"}
```
