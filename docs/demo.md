# Demo Walkthrough

No screen recording is included in this repo — this sandbox has no browser
to record one. This is the script to follow to demo it live or record your
own, in order, with what each step is meant to show.

## 1. Setup (once)

```bash
pip install -e ".[dev]"
cp .env.example .env        # fill in a real ANTHROPIC_API_KEY
alembic upgrade head
uvicorn src.main:app --reload
```

```bash
cd frontend
npm install
cp .env.example .env        # default already points at localhost:8000
npm run dev
```

Open `http://localhost:5173`.

## 2. Register and log in

Use the Register tab on the login screen (calls `POST /auth/register` then
`POST /auth/token`). Shows: JWT auth working end to end, password hashing
(bcrypt via passlib — never logged or stored in plaintext).

## 3. Research a lead

On the Leads page, enter a real company name (something with genuine,
findable AI-related signals works best for a good demo — e.g. an
AI-native startup you know of) and click Research.

**What's happening under the hood**, worth narrating live:
1. Research Agent runs an agentic tool-calling loop — it decides which
   `web_search` / `fetch_page` calls to make, not a fixed script.
2. Scoring Agent scores the research 0-100 against the ICP in
   `configs/icp_ai_native_b2b.yaml`.
3. If the score clears the reject threshold, Drafting Agent writes
   outreach; if not, the pipeline stops there — no wasted spend on a bad
   fit.
4. Guardrail Agent independently fact-checks the draft against the
   research. If it's rejected, Drafting Agent gets one revision pass with
   the guardrail's specific feedback before the lead is flagged for human
   review instead of auto-approved.

This call blocks for up to ~30 seconds (documented, deliberate tradeoff —
see Future Improvements in `docs/architecture.md`) — the button shows
"Running pipeline..." for the duration.

## 4. Lead detail page

Click into the researched lead. Shows, in order:

- **Research**: the summary and individual signals the Research Agent
  found, each with its source URL.
- **Score**: the 0-100 score, confidence, and the Scoring Agent's stated
  reasoning.
- **Outreach draft**: the message plus a clear guardrail-approved /
  guardrail-flagged badge.
- **Agent trace**: every agent invocation for this lead — including failed
  attempts and retries, not just the final result — with per-call latency,
  token counts, and estimated cost. This is the payoff of the `AgentLog`
  audit table: nothing about this pipeline's decisions is a black box.

## 5. (Optional) Demonstrate the fail-closed guardrail

Hard to force organically, but worth explaining even if not shown live:
if the Guardrail Agent's own LLM call fails (rate limit, outage), the
system does **not** default to "approved" — it fails closed, same as an
explicit rejection. `tests/agents/test_guardrail_agent.py` has the test
that proves this; point to it if asked in an interview setting.

## 6. (Optional) Show the audit trail surviving a real failure

`tests/agents/test_research_agent.py::test_research_company_handles_client_side_error_not_just_api_error`
is a regression test for a real bug found via live testing during
Milestone 13: a missing API key raises a client-side `TypeError`, not an
`anthropic.APIError` — the original `except anthropic.APIError` clause
didn't catch it, so the exception escaped uncaught, crashed the API with a
raw 500, and skipped the audit trail entirely. Worth mentioning as an
example of testing surfacing a real gap that mocked unit tests couldn't
have caught, since every existing test mocks the client and never exercises
real credential-resolution code.

## 7. Eval harness (terminal, not the UI)

```bash
python -m src.eval.run_eval
```

Runs the Scoring Agent against 25 labeled synthetic companies and prints
precision/recall/F1 per score band, agreement rate, and total cost. Shows
this isn't "vibes-based" agent quality — there's a repeatable, numeric way
to check whether a prompt or model change made scoring better or worse.
