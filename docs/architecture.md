# AI SDR — Multi-Agent Sales Lead Research & Qualification System
### Milestone 1: Problem Definition & Architecture Design

---

## 1. Problem Definition

**Statement:** Given a target company/lead, autonomously research it, score its fit against a defined Ideal Customer Profile (ICP), and produce a personalized, factually-grounded outreach draft — with every agent decision logged for human review before anything is sent.

**Why this scope:** Real AI SDR products (Clay, Artisan, 11x) do exactly this loop. Scoping to research → score → draft → guardrail keeps it buildable solo on CPU-only hardware in ~2 weeks while still being a legitimate product, not a toy.

**Explicit non-goals (for now, listed under Future Improvements):** no email-sending integration, no CRM sync, no multi-tenant billing. These are believable "V2" additions — good interview talking points, bad use of limited build time.

**Target user:** An SDR/sales manager who uploads a list of leads and gets back scored, researched, drafted outreach to review — not to blindly auto-send.

---

## 2. Success Metrics

| Metric | Target | Why it matters |
|---|---|---|
| Lead scoring agreement vs. human-labeled eval set | >80% | Proves the scoring logic isn't random — this is your "model evaluation" equivalent |
| Ungrounded/hallucinated claims in drafts | ~0% | Production LLM systems are judged on grounding, not fluency |
| End-to-end latency per lead | <30s | Shows you thought about UX/production latency, not just correctness |
| Agent decision traceability | 100% logged | Explainability requirement — every score/draft must show its reasoning chain |

---

## 3. Agent Architecture

```
                     ┌─────────────────┐
   Lead (company)───▶│   Orchestrator   │  (state machine, retries, persistence)
                     └────────┬─────────┘
                              │
              ┌───────────────┼────────────────┐
              ▼                                 
     ┌─────────────────┐                        
     │ Research Agent   │  tools: web_search, page_fetch
     │ → LeadProfile    │  output: structured company facts, signals, news
     └────────┬─────────┘
              ▼
     ┌─────────────────┐
     │ Scoring Agent    │  input: LeadProfile + ICP config
     │ → ScoreResult    │  output: score 0-100, reasoning, confidence
     └────────┬─────────┘
       score ≥ threshold?
              ▼
     ┌─────────────────┐
     │ Drafting Agent   │  input: LeadProfile + ScoreResult
     │ → OutreachDraft  │  output: personalized message referencing real signals
     └────────┬─────────┘
              ▼
     ┌─────────────────┐
     │ Guardrail Agent  │  checks: every claim in draft traces back to LeadProfile
     │ → Approved/Flag  │  (LLM-as-judge pattern — standard production practice)
     └────────┬─────────┘
              ▼
        Persist to DB → expose via API
```

**Why 4 specialized agents instead of 1 mega-prompt:** this is the core differentiator vs. typical single-agent portfolio projects. Each agent has one job, one tool set, one structured output schema — easier to test, evaluate, and reason about independently. It also lets us swap/upgrade one agent without touching others (e.g., swap the Research Agent's search tool later).

**Why a Guardrail Agent specifically:** hallucination is the #1 production risk in agentic systems. An explicit fact-checking step (comparing draft claims against the source LeadProfile) is exactly the kind of "I thought about production safety" detail that separates a portfolio project from a toy demo.

---

## 4. Tech Stack (and why)

| Layer | Choice | Reasoning |
|---|---|---|
| Backend API | FastAPI | Industry standard for AI Engineer roles; async, auto-generated OpenAPI docs, Pydantic-native (matches our structured agent I/O) |
| Agent orchestration | Hand-rolled state machine first → refactor to LangGraph | We build it by hand initially so you understand the tool-calling loop and state transitions at a low level (interview-relevant), then refactor to LangGraph as a documented improvement — LangGraph is what most companies actually use in production |
| LLM | Anthropic Claude API (you have credits) — **tiered model use**: Claude Haiku 4.5 for Research/Scoring Agents (high call volume, needs speed/cost efficiency), Claude Sonnet 5 for Drafting/Guardrail Agents (higher-stakes, quality-sensitive output) | Tiered model selection by task cost/risk is a real production cost-optimization pattern — using one expensive model for everything is a common junior mistake and a good interview talking point |
| Web search tool | `duckduckgo-search` (free, no key) with Tavily documented as a "prod upgrade" | Keeps dev cost at $0 while still demonstrating tool-use design |
| Database | PostgreSQL (Docker) via SQLAlchemy + Alembic | Relational fits lead/score/draft/log data well; matches what's used in real backend teams |
| Auth | JWT via FastAPI OAuth2PasswordBearer | Multi-user (sales team) access is realistic for this product |
| Logging | Structured JSON logging (every agent decision persisted, not just printed) | This *is* your explainability layer for an agentic system |
| Testing | pytest with mocked LLM/tool responses | Deterministic tests are non-negotiable for agent systems — real interviewers ask about this |
| Containerization | Docker + docker-compose (api + postgres) | Standard requirement, low effort given API-only workload |
| CI/CD | GitHub Actions (lint, test, build) | Signals engineering maturity beyond "it runs on my machine" |
| Deployment | Render or Railway (free/cheap tier, Docker + managed Postgres) | No GPU needed anywhere in this stack, so free-tier hosting is genuinely sufficient |
| Frontend | Deferred to its own later milestone — lightweight dashboard (leads, scores, drafts, agent trace viewer) | Kept out of MVP scope so agent quality isn't rushed to hit a UI deadline |

---

## 5. Folder Structure (industry `src` layout)

```
AI-SDR-Architecture/
├── src/
│   ├── api/              # FastAPI route handlers
│   ├── agents/           # research_agent.py, scoring_agent.py, drafting_agent.py, guardrail_agent.py, orchestrator.py
│   ├── tools/             # web_search.py, page_fetch.py
│   ├── core/              # config.py, security.py, logging.py
│   ├── db/                # models.py, session.py, migrations/
│   ├── schemas/           # Pydantic: LeadProfile, ScoreResult, OutreachDraft
│   ├── services/          # ties agents + db together
│   └── main.py
├── tests/
├── frontend/               # later milestone
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── .github/workflows/ci.yml
├── docs/
│   ├── architecture.md    # this file, evolved
│   └── architecture-diagram.png
├── .env.example
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## 6. Evaluation Plan

- Build a small hand-labeled eval set: ~25 mock companies with human-assigned "good fit / bad fit" labels against a defined ICP.
- Measure Scoring Agent agreement with human labels (precision/recall, not just accuracy — false positives are costly in real SDR workflows).
- Use an LLM-as-judge pass on Drafting Agent output to flag ungrounded claims (cross-referenced against Guardrail Agent's own output, as a sanity check on the sanity checker).
- Track latency and cost per lead run — production AI engineers are expected to reason about both, not just correctness.

---

## 7. 14-Day Milestone Plan

1. **Problem definition + architecture design** ✅
2. **Repo scaffolding, DB schema, core config** ✅
3. Research Agent + web search/scrape tools
4. Scoring Agent (structured output, ICP config)
5. Drafting Agent + Guardrail Agent
6. Orchestrator (hand-rolled state machine)
7. FastAPI endpoints + JWT auth
8. Logging + evaluation harness + eval dataset
9. Testing (unit + integration, mocked LLM)
10. Refactor orchestration to LangGraph (documented before/after comparison)
11. Docker + docker-compose
12. CI/CD (GitHub Actions)
13. Frontend dashboard
14. Deployment, README, architecture diagram, demo, future-improvements doc

---

## 8. Finalized Decisions

**LLM provider:** Anthropic Claude API (Haiku 4.5 for Research/Scoring, Sonnet 5 for Drafting/Guardrail — see tiering rationale in Section 4).

**ICP definition:** *AI-native B2B companies* — startups/scale-ups building AI products or adopting AI infrastructure (AI dev tools, agent platforms, MLOps, applied-AI SaaS). Chosen deliberately because:

- It's the single fastest-growing B2B buying category right now, meaning genuinely available, timely signal data to research (funding announcements, hiring for AI roles, product launches).
- It makes the project self-referential in a way that reads well in interviews: *"I built an AI SDR that sells to AI companies"* is a memorable, on-thesis pitch, not a generic "sells to any SaaS company" demo.
- Concrete scoring signals we'll extract: recent AI-related funding/press, job postings mentioning ML/AI engineer roles, product pages mentioning "AI," "agent," "LLM," "copilot," GitHub/tech presence indicating an engineering-heavy team.

Eval set (Milestone 8) will be ~25 real or realistic AI-native companies hand-labeled against this ICP.

---

## 9. Future Improvements (post-MVP, good interview talking points)

- Real email/CRM integration (Gmail API, HubSpot/Salesforce)
- Multi-tenant support with per-org ICP configs
- Swap DuckDuckGo for a paid enrichment API (Clearbit/Apollo) for higher-quality signals
- Human-in-the-loop approval queue in the frontend before any draft is marked "ready to send"
- Cost/latency dashboard per agent run
