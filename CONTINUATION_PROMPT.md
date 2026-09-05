# Continuation prompt — paste this into a new chat

I'm continuing work on my "AI SDR" portfolio project with you. Here's the full context so you don't need to re-discover anything. My connected folder is `D:\AI-SDR-Architecture` — read files there directly instead of asking me to re-paste content.

## What this project is

Two phases:
1. **AI SDR backend** — a multi-agent system (Research → Score → reject-early gate → Draft → Guardrail → one self-correction loop) that researches a company, scores it against a configurable ICP, drafts personalized outreach, and independently fact-checks the draft before marking it ready to send. Built with FastAPI, LangGraph, PostgreSQL/SQLAlchemy/Alembic, JWT auth, a React/Vite/TS dashboard, Docker, GitHub Actions CI, and a synthetic eval harness.
2. **Portfolio website** — a Vite + React + TypeScript + Tailwind v4 site ("Engineering Log" design: dark near-black background, JetBrains Mono + Source Serif 4, amber accent) at `D:\AI-SDR-Architecture\portfolio-site\`, featuring the AI SDR project plus my other resume projects, positioned for an AI/ML Engineer role.

## Current status (as of this prompt)

**Phase 1 backend: functionally complete, all 14 original milestones done, PLUS a full LLM-provider migration just finished:**
- Originally built on Anthropic Claude (paid). I don't have an Anthropic API key and don't want to pay, so we migrated the entire codebase to **Groq** (free tier, no credit card) using the `openai` Python SDK pointed at Groq's OpenAI-compatible endpoint (`base_url="https://api.groq.com/openai/v1"`). Groq's API mirrors OpenAI's Chat Completions shape (`tools`/`tool_calls`, forced `tool_choice`), so this was a client + response-parsing swap, not a redesign.
- Kept the **tiered two-model design**: `openai/gpt-oss-20b` (fast/cheap) for Research + Scoring, `openai/gpt-oss-120b` (stronger) for Drafting + Guardrail.
- Everything migrated: `src/core/config.py`, `src/core/pricing.py`, all 4 agents (`research_agent.py`, `scoring_agent.py`, `drafting_agent.py`, `guardrail_agent.py`), `orchestrator.py`, `orchestrator_legacy.py` (frozen historical reference, updated for consistency), `pyproject.toml` (`anthropic` → `openai>=1.50`), all test mocks rewritten to OpenAI-shaped fakes, `.env.example`, `render.yaml`, `docker-compose.yml`, `README.md`, `docs/architecture.md`, `docs/deployment.md`, `docs/demo.md`, `portfolio-site/src/data.ts`.
- **Verified**: `pytest` → 102/102 passing. `ruff check src tests` → clean. `render.yaml` and `docker-compose.yml` parse correctly.
- **Not yet done**: actually running it locally with a real `GROQ_API_KEY` (free, no card, sign up at console.groq.com/keys) and deploying it live to Render. I have a full step-by-step guide ready to walk through (Docker Compose up, frontend dev server, end-to-end smoke test, git commit/push, Render Blueprint deploy, the two-pass URL fix for CORS/dashboard-API cross-references, final live verification).

**Phase 2 portfolio site: built and content-complete.**
- All real content in place: resume, project list with real GitHub URLs, skills, certifications, professional photo (grayscale-filtered hero), resume PDF download.
- `npm run build` verified working (both in a scratch copy and in the real `D:\AI-SDR-Architecture\portfolio-site\` destination).
- I deployed it to Vercel myself (Root Directory setting: `portfolio-site`) — **status/live URL not yet confirmed back to Claude**, may need to check if it's actually live and working.
- **Not yet done**: once both projects are live, update `portfolio-site/src/data.ts`'s `featuredProject.demoUrl` and `githubUrl` placeholders (currently empty strings) with the real deployed URLs, and cross-link the two projects' READMEs to each other.

## Sandbox environment quirks worth knowing (if the new session hits weird errors)

- The mounted filesystem (both my `D:\AI-SDR-Architecture` folder and Claude's internal scratch folder) doesn't reliably support file deletion (`rm`/`unlink`) — `mv`/rename works fine. This breaks things like `.coverage` file cleanup (`pytest --cov` may throw `PermissionError` trying to erase it — just run plain `pytest` without `--cov` as a workaround) and can break `npm install` on heavier dependency trees.
- Next.js's install repeatedly failed in this environment (ENOTEMPTY errors); Vite installs cleanly and is the standard going forward for any frontend work here.
- Background shell processes do not survive between separate tool calls in this sandbox — anything long-running needs to complete within one call or be split into resumable steps.
- Playwright/Chromium can't be installed here (network allowlist blocks the download) — no live browser screenshots possible; verification relies on build success + content greps instead.

## My working style / standing instructions for this project

- Ask before major pivots or provider/architecture changes (this has been the pattern throughout — e.g. I was explicitly asked and picked Groq over Gemini, and picked "keep tiered models" over "collapse to one model").
- Verify claims — run the actual test suite/build/lint rather than asserting things work.
- Be honest about sandbox limitations rather than working around them silently (e.g. the Playwright limitation was disclosed, not hidden).
- I'm not a professional developer — I need things explained clearly and step by step, especially anything involving the terminal, git, or deployment. Assume I don't know background context unless I've demonstrated I do.
- Be concise and direct in chat responses generally.

## What I want to do next in this new chat

Pick up the **AI SDR local-run + deploy guide**, updated for Groq instead of Anthropic:
1. Confirm I've signed up for a free Groq API key and put it in `.env` as `GROQ_API_KEY`.
2. Walk me through running the full stack locally (Docker Compose for API+Postgres, or manual `uvicorn` + `alembic upgrade head`; frontend `npm run dev`).
3. Do an end-to-end smoke test (create a lead, watch it go through all 4 agents, check the trace viewer).
4. Git commit/push the Groq migration changes.
5. Deploy to Render via `render.yaml` (Blueprint), handle the two-pass URL/CORS fix.
6. Verify the live deployment actually works.
7. Then circle back to the portfolio site: confirm its Vercel deployment is live, and once both projects have real URLs, update `portfolio-site/src/data.ts`'s `demoUrl`/`githubUrl` and cross-link the READMEs.
