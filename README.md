# AI SDR — Multi-Agent Sales Lead Research & Qualification System

A multi-agent system that, given a company name, autonomously researches it,
scores it against a configurable Ideal Customer Profile, drafts personalized
outreach, and independently fact-checks that draft against the research
before anything is marked ready to send — with every agent decision logged
for full traceability. Not a chatbot wrapper: a pipeline with a fail-closed
guardrail, an audit trail, and an evaluation harness.

> Replace `<your-github-username>` below once this repo is pushed to
> GitHub, so the CI badge and links resolve.

[![CI](https://github.com/<your-github-username>/AI-SDR-Architecture/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-github-username>/AI-SDR-Architecture/actions/workflows/ci.yml)

**Live demo:** deploy via [`render.yaml`](render.yaml) — see
[`docs/deployment.md`](docs/deployment.md) — then link it here.

## What it does

1. **Research Agent** (Claude Haiku 4.5) — an agentic tool-calling loop
   (`web_search`, `fetch_page`) that gathers signals about a company:
   funding, hiring, product positioning.
2. **Scoring Agent** (Claude Haiku 4.5) — scores the research 0-100 against
   a weighted, YAML-configured ICP (currently: AI-native B2B companies).
   Below the reject threshold, the pipeline stops here — no wasted spend on
   drafting outreach to a bad-fit lead.
3. **Drafting Agent** (Claude Sonnet 5) — writes a personalized outreach
   message grounded in the research.
4. **Guardrail Agent** (Claude Sonnet 5) — independently fact-checks the
   draft against the research using a chain-of-verification pattern, and
   **fails closed**: if the guardrail check itself errors out, the draft is
   never auto-approved. One revision loop back through Drafting before a
   lead is flagged for human review.

Every agent call — including failed attempts and retries — is written to an
append-only `AgentLog` table (agent, model, latency, tokens, cost,
success/error), which the dashboard's trace viewer renders per lead.

![Architecture diagram](docs/architecture-diagram.svg)

## Key engineering decisions

A few choices worth calling out (full reasoning in
[`docs/architecture.md`](docs/architecture.md)):

- **Tiered model use** — cheap/fast Haiku 4.5 for the high-volume research
  and scoring steps, Sonnet 5 for the higher-stakes drafting and guardrail
  steps. Using one expensive model for everything is a common and avoidable
  cost mistake.
- **Fail-closed guardrail** — an LLM outage during the fact-check step
  results in a flagged lead, never a silently-approved one.
- **Hand-rolled orchestrator first, LangGraph second** — the pipeline was
  built as an explicit state machine before being refactored onto
  LangGraph, specifically so the low-level tool-calling and state-transition
  logic wasn't hidden behind a framework from day one. Both versions exist
  side by side; see [`docs/milestone10-langgraph-refactor.md`](docs/milestone10-langgraph-refactor.md)
  for the before/after comparison, including the honest finding that the
  LangGraph version is *more* lines of code, not fewer.
  Rewriting agent orchestration a second time, on purpose, to compare two real
  implementations against the same test suite is a big part of why this
  project exists rather than a simpler single-agent demo.
- **Manual retries, not LangGraph's `RetryPolicy`** — agents return `Result`
  objects (`success: bool`) rather than raising exceptions on failure, so a
  native retry-on-exception policy would never trigger. `call_with_retry`
  wraps every node instead.
- **Dialect-generic SQLAlchemy types** — `Uuid`, not
  `postgresql.dialects.UUID`, so the full test suite runs against in-memory
  SQLite without needing a real Postgres instance for unit tests.
- **Synchronous pipeline execution** — `POST /leads` blocks until all four
  agents finish (documented tradeoff, not an oversight — see Future
  Improvements). Fine for a single-user demo; a background task queue is
  the obvious next step under concurrent load.

## Tech stack

| Layer | Choice |
|---|---|
| Backend API | FastAPI, JWT auth (OAuth2PasswordBearer) |
| Agent orchestration | LangGraph `StateGraph` (hand-rolled version preserved as reference) |
| LLM | Anthropic Claude — Haiku 4.5 + Sonnet 5, tiered by task |
| Database | PostgreSQL via SQLAlchemy 2.0 + Alembic |
| Frontend | React + Vite + TypeScript, `react-router-dom` |
| Testing | pytest, mocked LLM/tool responses, 96%+ coverage |
| CI/CD | GitHub Actions — lint, test, then a real Docker build + smoke test |
| Containerization | Docker (multi-stage, non-root) + docker-compose |
| Deployment | Render Blueprint (`render.yaml`) — see [`docs/deployment.md`](docs/deployment.md) |

Full rationale for every choice in [`docs/architecture.md`](docs/architecture.md) §4.

## Local development

Backend:

```bash
pip install -e ".[dev]"
cp .env.example .env  # fill in your Anthropic API key
alembic upgrade head
uvicorn src.main:app --reload
```

Frontend dashboard (separate terminal):

```bash
cd frontend
npm install
cp .env.example .env  # points at http://localhost:8000 by default
npm run dev
```

Open `http://localhost:5173`, register an account, and research a lead.
See [`docs/demo.md`](docs/demo.md) for a full walkthrough.

## Testing and evaluation

```bash
pytest --cov=src --cov-report=term-missing   # unit + integration tests
ruff check src tests                          # lint
python -m src.eval.run_eval                   # scoring accuracy against 25 labeled synthetic companies
```

The eval harness (`src/eval/run_eval.py`) reports precision/recall/F1 per
score band (reject/review/ready), agreement rate, mean latency, and total
cost against `data/eval/ai_native_b2b_eval_set.yaml` — 25 fictional
companies, deliberately synthetic rather than scraped real ones, so the
eval is reproducible and isolates Scoring Agent quality from Research
Agent/web variability. It requires a real `ANTHROPIC_API_KEY` to run (it
calls the Scoring Agent directly) — not executed in this repo's own build
environment, which has no key configured; run it locally to see current
numbers.

## Docker

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Project structure

```
AI-SDR-Architecture/
├── src/
│   ├── api/          # FastAPI routers: auth, leads, health, middleware
│   ├── agents/        # research, scoring, drafting, guardrail + orchestrator
│   ├── tools/          # web_search, page_fetch
│   ├── core/            # config, security, logging, pricing, ICP loader
│   ├── db/                # SQLAlchemy models, session
│   ├── schemas/            # Pydantic I/O contracts
│   ├── services/            # lead_service.py — orchestrator -> DB
│   └── eval/                 # evaluation harness
├── frontend/                   # React + Vite + TS dashboard
├── tests/                        # mirrors src/, mocked-LLM unit tests
├── alembic/                        # DB migrations
├── docker/                          # Dockerfile, docker-compose.yml
├── .github/workflows/ci.yml          # lint -> test -> real Docker build+smoke test
├── configs/                            # ICP YAML config
├── data/eval/                            # synthetic eval dataset
├── docs/                                   # architecture, deployment, demo docs
└── render.yaml                               # one-file Render Blueprint
```

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — problem definition, full
  architecture, tech stack rationale, milestone plan, future improvements
- [`docs/milestone10-langgraph-refactor.md`](docs/milestone10-langgraph-refactor.md) —
  hand-rolled state machine vs. LangGraph, compared directly
- [`docs/deployment.md`](docs/deployment.md) — Render deployment guide
- [`docs/demo.md`](docs/demo.md) — end-to-end walkthrough
